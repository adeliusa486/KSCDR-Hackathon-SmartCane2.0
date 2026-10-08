# Objects the cane knows

The detector names **152 kinds of object**. Each one is spoken as "name, direction, distance", for example "chair ahead, 1.3 meters" or "car left, about 4 meters". Anything the model is not sure of (confidence under 0.35), or anything it was never trained on, is announced as "obstacle" with its direction and distance, so nothing physical is silently dropped.

How to read the tables:

- **Urgency**: rank in the speech order (1 = said first). Drop-offs come first, then vehicles, then people and animals, then street obstacles. Unranked objects follow, nearest first.
- **Train boxes**: labelled examples in the training set (human labels plus checked pseudo-labels).
- **mAP50 / recall**: accuracy of smartcane152_v3 on 27,906 validation images. Recall is the share of real objects found. Above 0.7 mAP50 is reliable, 0.5 to 0.7 usable, under 0.5 often heard as "obstacle" instead of its name.
- **Camera distance**: yes = the camera estimates the distance in metres from the object's typical height. Straight ahead, the forward ToF sensor measures it instead.

## People and mobility

| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |
|---|---|---|---|---|---|
| person | 18 | 368,939 | 0.81 | 0.76 | yes |
| child | 19 | 19,670 | 0.33 | 0.16 | yes |
| cyclist | 16 | 1,980 | 0.39 | 0.36 | yes |
| motorcyclist | 17 | 1,980 | 0.40 | 0.33 | yes |
| wheelchair |  | 1,720 | 0.83 | 0.79 | yes |
| stroller |  | 2,451 | 0.88 | 0.89 | yes |

## Animals

| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |
|---|---|---|---|---|---|
| dog | 20 | 8,429 | 0.84 | 0.79 | yes |
| cat |  | 5,197 | 0.87 | 0.83 | yes |
| bird |  | 9,733 | 0.61 | 0.57 |  |
| horse | 22 | 7,067 | 0.80 | 0.74 | yes |
| cow | 21 | 11,007 | 0.70 | 0.61 | yes |
| sheep |  | 9,406 | 0.76 | 0.75 | yes |
| goat |  | 2,515 | 0.64 | 0.58 | yes |
| camel |  | 1,390 | 0.65 | 0.63 | yes |

## Vehicles

| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |
|---|---|---|---|---|---|
| car | 7 | 252,033 | 0.81 | 0.76 | yes |
| bus | 8 | 13,514 | 0.73 | 0.67 | yes |
| truck | 9 | 24,153 | 0.65 | 0.64 | yes |
| van | 10 | 3,743 | 0.58 | 0.47 | yes |
| taxi | 11 | 4,941 | 0.64 | 0.49 | yes |
| ambulance |  | 524 | 0.53 | 0.49 | yes |
| motorcycle | 12 | 16,763 | 0.75 | 0.70 | yes |
| bicycle | 14 | 18,199 | 0.67 | 0.60 | yes |
| e-scooter | 15 | 3,818 | 0.91 | 0.85 | yes |
| skateboard |  | 3,742 | 0.70 | 0.65 |  |
| train | 13 | 4,437 | 0.85 | 0.80 |  |
| golf cart |  | 606 | 0.68 | 0.65 |  |
| shopping cart |  | 2,595 | 0.57 | 0.50 |  |
| trailer |  | 216 | 0.00 | 0.00 |  |

## Ground hazards and level changes

| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |
|---|---|---|---|---|---|
| open hole | 1 | 1,132 | 0.81 | 0.83 |  |
| pothole | 3 | 9,171 | 0.50 | 0.51 |  |
| manhole | 4 | 9,165 | 0.23 | 0.20 |  |
| storm drain |  | 4,829 | 0.14 | 0.10 |  |
| stairs | 2 | 3,408 | 0.60 | 0.53 |  |
| escalator |  | 536 | 0.53 | 0.60 |  |
| curb | 5 | 56,366 | 0.24 | 0.17 |  |
| curb ramp |  | 15,354 | 0.02 | 0.00 |  |
| ramp |  | 2,046 | 0.32 | 0.29 |  |
| speed bump |  | 1,765 | 0.75 | 0.65 |  |
| sidewalk crack |  | 1,386 | 0.02 | 0.05 |  |
| rail track | 6 | 891 | 0.29 | 0.30 |  |
| tactile paving |  | 356 | 0.63 | 0.64 |  |
| swimming pool |  | 2,206 | 0.81 | 0.72 |  |

## Crossings, signals and signs

| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |
|---|---|---|---|---|---|
| crosswalk | 30 | 15,777 | 0.22 | 0.16 |  |
| traffic light | 28 | 44,208 | 0.71 | 0.67 |  |
| pedestrian signal | 29 | 6,907 | 0.28 | 0.21 |  |
| crosswalk button |  | 182 | 0.85 | 0.67 |  |
| stop sign | 31 | 1,495 | 0.69 | 0.67 |  |
| traffic sign |  | 127,769 | 0.57 | 0.54 |  |
| yield sign |  | 866 | 0.44 | 0.40 |  |
| do not enter sign |  | 416 | 0.33 | 0.24 |  |
| one way sign |  | 801 | 0.03 | 0.00 |  |
| pedestrian crossing sign |  | 1,677 | 0.44 | 0.45 |  |
| speed limit sign |  | 2,264 | 0.45 | 0.43 |  |
| construction sign |  | 298 | 0.27 | 0.07 |  |
| sidewalk closed sign |  | 171 | 0.83 | 0.86 |  |
| bus stop sign |  | 126 | 0.17 | 0.00 |  |
| exit sign |  | 1,201 | 0.52 | 0.62 |  |
| wet floor sign |  | 1,014 | 0.95 | 0.91 | yes |

## Street furniture and obstacles

| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |
|---|---|---|---|---|---|
| pole | 26 | 84,065 | 0.32 | 0.23 |  |
| utility pole | 27 | 25,989 | 0.37 | 0.28 |  |
| street light |  | 40,813 | 0.44 | 0.37 |  |
| bollard | 25 | 10,345 | 0.50 | 0.45 | yes |
| traffic cone | 23 | 2,884 | 0.59 | 0.55 | yes |
| barrier | 24 | 5,936 | 0.33 | 0.29 |  |
| fence |  | 23,209 | 0.14 | 0.09 |  |
| barrel |  | 2,493 | 0.69 | 0.74 | yes |
| fire hydrant | 32 | 2,180 | 0.67 | 0.60 | yes |
| parking meter |  | 1,187 | 0.63 | 0.57 | yes |
| bench | 33 | 11,793 | 0.47 | 0.46 | yes |
| trash can |  | 6,209 | 0.44 | 0.40 | yes |
| bike rack |  | 941 | 0.04 | 0.00 |  |
| mailbox |  | 425 | 0.01 | 0.00 | yes |
| utility box |  | 3,127 | 0.18 | 0.14 | yes |
| billboard |  | 29,988 | 0.27 | 0.19 |  |
| sidewalk sign |  | 2,818 | 0.33 | 0.40 |  |
| kiosk |  | 136 | 0.27 | 0.00 | yes |
| fountain |  | 2,258 | 0.54 | 0.46 |  |
| sculpture |  | 4,056 | 0.52 | 0.49 |  |
| pillar |  | 152 | 0.00 | 0.00 |  |
| ladder |  | 1,162 | 0.82 | 0.77 | yes |
| tent |  | 3,565 | 0.60 | 0.56 |  |
| potted plant |  | 32,154 | 0.63 | 0.63 | yes |

## Buildings and entrances

| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |
|---|---|---|---|---|---|
| door |  | 5,775 | 0.44 | 0.39 | yes |
| door handle |  | 975 | 0.56 | 0.52 |  |
| window |  | 51,595 | 0.40 | 0.35 |  |
| building |  | 74,895 | 0.49 | 0.42 |  |
| elevator |  | 2,871 | 0.89 | 0.82 | yes |
| atm |  | 376 | 0.39 | 0.37 | yes |

## Trees and plants

| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |
|---|---|---|---|---|---|
| tree |  | 83,695 | 0.61 | 0.52 |  |
| palm tree |  | 9,966 | 0.53 | 0.47 |  |
| plant |  | 20,611 | 0.09 | 0.04 |  |

## Furniture

| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |
|---|---|---|---|---|---|
| chair |  | 72,978 | 0.67 | 0.62 | yes |
| stool |  | 1,455 | 0.62 | 0.67 | yes |
| couch |  | 7,052 | 0.69 | 0.66 | yes |
| bed |  | 6,456 | 0.82 | 0.80 | yes |
| table |  | 30,533 | 0.55 | 0.48 | yes |
| desk |  | 6,682 | 0.43 | 0.27 | yes |
| coffee table |  | 4,697 | 0.43 | 0.38 | yes |
| nightstand |  | 2,588 | 0.63 | 0.54 | yes |
| chest of drawers |  | 3,213 | 0.54 | 0.42 | yes |
| wardrobe |  | 304 | 0.43 | 0.41 | yes |
| cabinet |  | 16,830 | 0.23 | 0.09 | yes |
| shelf |  | 18,481 | 0.20 | 0.07 |  |
| bookcase |  | 4,747 | 0.61 | 0.54 | yes |
| countertop |  | 5,496 | 0.31 | 0.20 |  |
| mirror |  | 1,885 | 0.51 | 0.46 |  |
| curtain |  | 4,912 | 0.61 | 0.58 |  |
| lamp |  | 3,735 | 0.47 | 0.41 |  |
| ceiling fan |  | 632 | 0.76 | 0.76 |  |
| pillow |  | 5,919 | 0.54 | 0.51 |  |
| clock |  | 4,860 | 0.72 | 0.68 |  |

## Bathroom and kitchen

| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |
|---|---|---|---|---|---|
| toilet |  | 3,630 | 0.79 | 0.74 | yes |
| sink |  | 6,381 | 0.69 | 0.66 | yes |
| bathtub |  | 805 | 0.76 | 0.65 |  |
| shower |  | 307 | 0.29 | 0.22 |  |
| refrigerator |  | 2,894 | 0.67 | 0.69 | yes |
| microwave |  | 2,440 | 0.76 | 0.72 |  |
| oven |  | 3,721 | 0.60 | 0.58 | yes |
| stove |  | 1,210 | 0.43 | 0.47 | yes |
| washing machine |  | 775 | 0.77 | 0.69 | yes |
| kettle |  | 721 | 0.58 | 0.42 |  |
| towel |  | 337 | 0.28 | 0.23 |  |
| toothbrush |  | 1,168 | 0.31 | 0.32 |  |

## Electronics

| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |
|---|---|---|---|---|---|
| tv |  | 9,184 | 0.85 | 0.83 |  |
| laptop |  | 9,398 | 0.82 | 0.79 |  |
| keyboard |  | 5,349 | 0.79 | 0.79 |  |
| mouse |  | 2,672 | 0.77 | 0.76 |  |
| remote |  | 2,724 | 0.52 | 0.52 |  |
| cell phone |  | 6,349 | 0.67 | 0.66 |  |

## Things you carry or find

| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |
|---|---|---|---|---|---|
| backpack |  | 6,630 | 0.43 | 0.44 | yes |
| handbag |  | 9,901 | 0.46 | 0.44 |  |
| suitcase |  | 5,852 | 0.52 | 0.51 | yes |
| umbrella |  | 10,365 | 0.65 | 0.64 |  |
| glasses |  | 8,776 | 0.59 | 0.49 |  |
| book |  | 43,178 | 0.43 | 0.46 |  |
| bottle |  | 24,996 | 0.68 | 0.67 |  |
| cup |  | 23,795 | 0.70 | 0.67 |  |
| can |  | 3,176 | 0.69 | 0.75 |  |
| box |  | 4,292 | 0.46 | 0.45 | yes |
| plastic bag |  | 1,055 | 0.50 | 0.59 |  |
| tire |  | 24,355 | 0.53 | 0.45 |  |
| ball |  | 6,040 | 0.63 | 0.62 |  |
| toy |  | 9,320 | 0.29 | 0.26 |  |
| scissors |  | 1,078 | 0.53 | 0.55 |  |
| knife |  | 4,832 | 0.49 | 0.52 |  |
| fork |  | 5,069 | 0.64 | 0.58 |  |
| spoon |  | 6,046 | 0.53 | 0.47 |  |
| bowl |  | 14,472 | 0.71 | 0.68 |  |
| plate |  | 5,243 | 0.54 | 0.51 |  |
| banana |  | 5,585 | 0.52 | 0.51 |  |
| apple |  | 7,393 | 0.64 | 0.62 |  |
| orange |  | 10,252 | 0.63 | 0.65 |  |

## Totals

152 classes, 2,168,416 labelled boxes in the training split. Validation: mAP50 0.535, mAP50-95 0.376 over all classes.

Generated by `docs/make_objects.py` from the model's label file, `data/merged_v2/class_counts.csv` and `docs/results/v3_per_class.csv`.
