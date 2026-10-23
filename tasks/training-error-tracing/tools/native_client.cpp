#include <cerrno>
#include <cctype>
#include <cstring>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <sys/socket.h>
#include <sys/un.h>
#include <fcntl.h>
#include <unistd.h>

static void write_all(int fd, const std::string &value) {
    size_t offset = 0;
    while (offset < value.size()) {
        ssize_t n = write(fd, value.data()+offset, value.size()-offset);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) throw std::runtime_error("write failed");
        offset += size_t(n);
    }
}

static std::string compact(const std::string &raw) {
    std::string out;
    bool quoted = false, escaped = false;
    for (unsigned char c : raw) {
        if (quoted) {
            out += char(c);
            if (escaped) escaped = false;
            else if (c == '\\') escaped = true;
            else if (c == '"') quoted = false;
        } else if (c == '"') { quoted = true; out += char(c); }
        else if (!std::isspace(c)) out += char(c);
    }
    return out;
}

int main(int argc, char **argv) {
    try {
        std::string index, query, output;
        if (argc != 9) return 2;
        for (int i=1; i<argc; i+=2) {
            std::string flag(argv[i]), value(argv[i+1]);
            if (flag == "--index-dir") index = value;
            else if (flag == "--query") query = value;
            else if (flag == "--output") output = value;
            else if (flag != "--top-k" || value != "10") return 2;
        }
        if (index.empty() || query.empty() || output.empty()) return 2;
        std::ifstream source(query);
        if (!source) return 3;
        std::string raw((std::istreambuf_iterator<char>(source)), {});
        if (raw.size() > 1024*1024) return 3;
        sockaddr_un address{};
        address.sun_family = AF_UNIX;
        std::string socket_path = index+"/retriever.sock";
        if (socket_path.size() >= sizeof(address.sun_path)) return 3;
        std::memcpy(address.sun_path, socket_path.c_str(), socket_path.size()+1);
        int connection = socket(AF_UNIX, SOCK_STREAM, 0);
        if (connection < 0 || connect(connection, reinterpret_cast<sockaddr*>(&address), sizeof(address))) return 4;
        write_all(connection, "{\"action\":\"query\",\"query\":"+compact(raw)+"}\n");
        std::string response;
        char buffer[4096];
        while (response.find('\n') == std::string::npos) {
            ssize_t count = read(connection, buffer, sizeof(buffer));
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) return 5;
            response.append(buffer, size_t(count));
            if (response.size() > 65536) return 5;
        }
        close(connection);
        int target = open(output.c_str(), O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0600);
        if (target < 0) return 6;
        write_all(target, response);
        if (close(target)) return 6;
        return 0;
    } catch (...) { return 1; }
}
