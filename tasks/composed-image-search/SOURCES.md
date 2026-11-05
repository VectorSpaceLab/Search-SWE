# Sources and Preparation

This is package provenance for authors and reviewers. It is not mounted into
the agent environment; runtime resource permissions remain in the task instruction
and environment documentation.

## Dataset and preparation

[CIRCO](https://github.com/miccunifi/CIRCO) contributes 216 original
multiple-positive requests over the COCO 2017 unlabeled gallery.
[CIRR validation captions](https://github.com/Cuberick-Orion/CIRR/tree/cirr_dataset/captions)
contribute 4,181 original requests and 2,297 images, matched to the
[fixed image mirror](https://huggingface.co/datasets/royokong/cirr_imgs/tree/7a25e03bc7640ef61d80b854e3c9762871d74a28).

The shared gallery has 125,226 images. IDs are remapped, while image bytes,
modification requests and source targets are retained. CIRR's missing
shared-concept annotation remains empty. No generated request or target is added.
CIRCO's AP metrics and CIRR's recall metrics are averaged within source, then
the sources receive equal weight. The joint gallery and combined metric are
task adaptations. No precomputed image or query vectors are supplied.

The current package has 5 public input rows and 4,392 held-out rows.

## Source terms

[CIRCO's upstream notice](https://github.com/miccunifi/CIRCO#license) states CC BY-NC 4.0, requiring attribution, noncommercial use and identification of modifications. The [CIRR repository notice](https://github.com/Cuberick-Orion/CIRR/blob/cirr_dataset/LICENSE) is MIT for the released software and associated material. Gallery photographs retain their original image rights, including the [COCO source terms](https://cocodataset.org/#termsofuse); those rights are not replaced by the annotation or software licenses. Retain CIRCO/CIRR/COCO attribution and review coverage of the mirrored photographs. CLIP's [original notice](https://github.com/openai/CLIP/blob/main/LICENSE) is MIT.

## Runtime asset sources

| Repository | Type | Immutable revision | Files |
| --- | --- | --- | ---: |
| openai/clip-vit-base-patch32 | model | 3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268 | 8 |
| search-swe/Search-SWE | dataset | 123a7045916faf4ba98422a6f9f4f2d4f047cdc9 | 125,229 |

The manifest records exact task-relative paths and asset bytes. Source pins do
not change the corpus, examples, labels or model weights. Original upstream
source and model notices continue to apply.
