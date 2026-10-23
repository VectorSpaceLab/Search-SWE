"""Unchanged supplied APEX search, with ordinal-ID adapter only."""
from pathlib import Path
import torch
from library import Library
from apex.data.atom_bond_features import Vocabulary
from apex.nn.apex import APEXFactorizedCSL, APEXFactorizer
from apex.nn.encoder import LigandEncoder
from apex.nn.probe import LinearProbe


def prepare(library_dir,model_dir,index_dir):
    pass


class Searcher:
    def __init__(self,library_dir,model_dir,index_dir):
        torch.set_num_threads(16)
        Vocabulary.register_atom_vocab(); Vocabulary.register_bond_vocab()
        self.library=Library(library_dir)
        models=Path(model_dir)
        encoder=LigandEncoder.load(models/'encoder.pt',map_location='cpu')
        probe=LinearProbe.load(models/'probe.pt',map_location='cpu')
        factorizer=APEXFactorizer.load(models/'factorizer_brics_csl_12M.pt',map_location='cpu')
        self.model=APEXFactorizedCSL(encoder,factorizer,self.library.dataset,probe).eval()
        self.model.load_state_dict(torch.load(models/'apex_brics_csl_12M.pt',map_location='cpu',weights_only=True)['model_state_dict'])
        self.model=self.model.cuda()

    def search(self,query):
        frame=self.model.run_apex_search(k=query['k'],objective='score_'+query['target'],constraints=query['constraints'],maximize=False)
        return [self.library.name_to_id(name) for name in frame['name']]
