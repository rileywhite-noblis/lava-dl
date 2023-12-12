from video_dataset import VideoFrameDataset
import os
from torchvision import transforms
import torch
import numpy as np
from torch.utils.data import WeightedRandomSampler


def init_dataloader(partition="train", batch_size=8, num_frames_per_sample=100):
    videos_root = os.path.join("/ssd2/users/pweidel/datasets/NTU/data_frames/")
    annotation_file = os.path.join(videos_root, partition + '.txt')

    # classify_labels = [5, 6, 8, 9, 14, 15, 43, 51, 23, 27, 48]
    classify_labels = [41, 42, 43, 44, 45, 46, 47, 48, 104]
    
    preprocess = transforms.Compose([
        transforms.Resize(256, antialias=None),  # image batch, resize smaller edge to 256
        transforms.CenterCrop(224),  # image batch, center crop to square 224x224
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    
    dataset = VideoFrameDataset(
        root_path=videos_root,
        annotationfile_path=annotation_file,
        num_segments=num_frames_per_sample,
        frames_per_segment=1,
        imagefile_template='img_{:05d}.jpg',
        transform=preprocess,
        test_mode=False if partition == "train" else True,
        classify_labels = classify_labels 
    )

    if not partition == 'train':
        dataset.balance_by_random_drop()
    
    # example using inverse class frequencies
    sample_labels = dataset.label_list # list/array of labels
    class_counts = np.bincount(sample_labels)
    num_classes = len(class_counts)
    samples_per_class = np.min(class_counts)
    class_weights = 1. / class_counts   # assuming labels are class indices
    sample_weights = class_weights[sample_labels]

    
    # sampler = WeightedRandomSampler(sample_weights, num_samples=len(sample_weights))
    sampler = WeightedRandomSampler(sample_weights,
                                    num_samples=int(samples_per_class * num_classes),
                                    replacement=True)

    
    dataloader = torch.utils.data.DataLoader(
        dataset=dataset,
        batch_size=batch_size,
        num_workers=batch_size,
        pin_memory=True,
        sampler=sampler if partition == 'train' else None,
        shuffle=False if partition == 'train' else True,
    )

    return dataloader