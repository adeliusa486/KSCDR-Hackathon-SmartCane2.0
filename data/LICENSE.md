# Licences of the training data

The MIT licence at the root of this repository covers the code, firmware,
documentation and figures. It does **not** cover the files in `data/`, which
are derived from public datasets and keep their licences:

| Labels derived from | Licence | What it allows |
|---|---|---|
| COCO 2017 annotations | CC BY 4.0 | Any use with attribution |
| Open Images V7 annotations | CC BY 4.0 | Any use with attribution |
| Roboflow Universe projects listed in `code/training/roboflow_sources.yaml` | CC BY 4.0 (19 projects), Public Domain (1) | Any use with attribution |
| Mapillary Vistas v2 (`vistas__` files) | CC BY-NC-SA 4.0 | Non-commercial use, share under the same licence |
| Mapillary Traffic Sign Dataset (`mtsd__` files) | Mapillary research terms | Research use. Commercial use needs a licence from Mapillary |
| Pseudo-labels added by the teacher models | Same as the image they belong to | |

The images themselves are not in this repository. Fetch them from the original
datasets under those datasets' own terms. Anyone using the cane's model or labels
commercially must remove or replace the Vistas and MTSD contributions first.

Attribution: COCO (Lin et al., 2014), Open Images V7 (Kuznetsova et al., 2020),
Mapillary Vistas (Neuhold et al., ICCV 2017), Mapillary Traffic Sign Dataset
(Ertler et al., ECCV 2020), and the Roboflow Universe authors named in
`roboflow_sources.yaml`.
