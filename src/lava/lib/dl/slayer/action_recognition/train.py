import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--model', type=str, help='Model to train on. See model registry in model.py for a list of available models (efficientnet-b0-LSTM, efficientnet-b0-S4D, ..).')
parser.add_argument('--batch-size', type=int, default=8, help='Batch size. Default: 8')
parser.add_argument('--epochs', type=int, default=100, help='Num epochs. Default: 100')
parser.add_argument('--print-interval', type=int, default=100, help='Print information each N batches. Default: 100')
parser.add_argument('--lr', type=float, metavar="LEARNING_RATE", default=1e-3, help='Learning rate. Default: 1e-3')
parser.add_argument('--frames-per-sample', type=int, default=30, help='Num frames per sample. Default: 30')
# model arguments
parser.add_argument('--s4d-dims', type=int, default=1280, help='Num dimensions in S4D. Should not be changed, as it must match the output dimensions of Efficientnet. Default: 1280')
parser.add_argument('--s4d-states', type=int, default=1, help='Num of states per dimension in S4D. Default: 1')
parser.add_argument('--s4d-is-complex', action='store_true', help='Limit S4D to use real-numbers istead of complex.')
parser.add_argument('--s4d-lr', type=float, default=1e-3, help='Learning rate of S4D. Default: 1e-3')
parser.add_argument('--lstm-dims', type=int, default=1280, help='Num of states per dimension in S4D. Default: 1280')
parser.add_argument('--readout-hidden-dims', type=int, default=64, help='Size of the hidden layer of the readout MLP. Default: 64')
parser.add_argument('--efficientnet-activation', type=str, default="silu", help='Activation function used by Efficientnet (relu or silu). Default: silu')
args = parser.parse_args()

import matplotlib
matplotlib.use('Agg')
from model import model_registry 
from video_dataset import VideoFrameDataset, ImglistToTensor
import os
import torch
from torch import nn
from torch import optim
import time
import numpy as np
from dataloaders import init_dataloader
from torch.utils.tensorboard import SummaryWriter
from sklearn.metrics import ConfusionMatrixDisplay, accuracy_score
from datetime import datetime


# Params
learning_rate = args.lr 
num_epochs = args.epochs 
print_interval = args.print_interval 
batch_size = args.batch_size
num_frames_per_sample = args.frames_per_sample
args.s4d_is_real = False if args.s4d_is_complex else True
model_cls = model_registry[args.model] 
model_params = {"lstm_num_hidden": args.lstm_dims,
                "num_readout_hidden": args.readout_hidden_dims,
                "s4d_num_hidden": args.s4d_dims,
                "s4d_states": args.s4d_states,
                "s4d_is_real": args.s4d_is_real,
                "s4d_lr": args.s4d_lr,
                "efficientnet_activation": args.efficientnet_activation
                }

print(model_params)

train_dataloader = init_dataloader(partition="train",
                                   batch_size=batch_size,
                                   num_frames_per_sample=num_frames_per_sample) 
val_dataloader = init_dataloader(partition="val",
                                 batch_size=batch_size,
                                 num_frames_per_sample=num_frames_per_sample) 

num_classes = len(train_dataloader.dataset.label_map) + 1
model = model_cls(num_classes=num_classes, **model_params).cuda()


# Define your loss function
criterion = nn.CrossEntropyLoss()
# Define your optimizer
optimizer = optim.Adam(model.parameters(), lr=learning_rate)
writer = SummaryWriter(f'runs/NTU/{args.model}/{datetime.today().strftime("%Y-%m-%d %H:%M:%S")}')
writer.add_hparams(model_params, {"lr": args.lr})

print("start training")

epoch_loss = []
val_loss = []
min_val_loss = np.inf
# Training loop
for epoch in range(num_epochs):
    model.train()
    epoch_loss.append(0)
    preds = []
    tgts = []

    for batch_idx, (inputs, targets) in enumerate(train_dataloader):
        # Forward pass
        outputs = model(inputs.cuda())
        loss = criterion(outputs, targets.cuda().long())

        # Backward pass and optimization
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        pred = torch.argmax(outputs, dim=1).detach().cpu().numpy().tolist()
        preds += pred
        tgt = targets.cpu().numpy().tolist()
        tgts += tgt
        with torch.no_grad():
            if batch_idx % print_interval == 0:
                print(f'Epoch [{epoch+1}/{num_epochs}], Batch [{batch_idx+1}/{len(train_dataloader)}], Loss: {loss.item()}')
                print(f'pred {pred}, targets {tgt} acc {accuracy_score(tgts, preds)}')
        
        epoch_loss[-1] += loss.item()

    cm = ConfusionMatrixDisplay.from_predictions(tgts, preds)
    cm_norm = ConfusionMatrixDisplay.from_predictions(tgts, preds, normalize='true')
    train_acc = cm.confusion_matrix.diagonal() / cm.confusion_matrix.sum(axis=1)
    writer.add_scalar("Train Loss", epoch_loss[-1] / len(train_dataloader), epoch)
    writer.add_scalar("Train Accuracy", np.mean(train_acc), epoch)
    writer.add_figure("Train Confusion matrix", cm.figure_, epoch)
    writer.add_figure("Train Confusion matrix (normalized)", cm_norm.figure_, epoch)
    
    print(f"Avg loss on epoch {epoch}: {np.array(epoch_loss) / len(train_dataloader)}")


    model.eval()
    with torch.no_grad():
        val_loss.append(0)
        val_preds = []
        val_tgts = []

        for batch_idx, (inputs, targets) in enumerate(val_dataloader):
            # Forward pass
            outputs = model(inputs.cuda())
            loss = criterion(outputs, targets.cuda().long())

            pred = torch.argmax(outputs, dim=1).detach().cpu().numpy().tolist()
            val_preds += pred
            tgt = targets.cpu().numpy().tolist()
            val_tgts += tgt
            if batch_idx % print_interval == 0:
                print(f'Epoch [{epoch+1}/{num_epochs}], Batch [{batch_idx+1}/{len(val_dataloader)}], Loss: {loss.item()}')
                print(f'pred {pred}, targets {tgt} acc {accuracy_score(val_tgts, val_preds)}')
            
            val_loss[-1] += loss.item()

    cm = ConfusionMatrixDisplay.from_predictions(val_tgts, val_preds)
    cm_norm = ConfusionMatrixDisplay.from_predictions(val_tgts, val_preds, normalize='true')
    val_acc = cm.confusion_matrix.diagonal() / cm.confusion_matrix.sum(axis=1)

    writer.add_scalar("Val Loss", val_loss[-1] / len(val_dataloader), epoch)
    writer.add_scalar("Val Accuracy", np.mean(val_acc), epoch)
    writer.add_figure("Val Confusion matrix", cm.figure_, epoch)
    writer.add_figure("Val Confusion matrix (normalized)", cm_norm.figure_, epoch)

    
    if val_loss[-1] < min_val_loss:
        min_val_loss = val_loss[-1]
        # Save the trained model (optional)
        torch.save(model.state_dict(), f'{args.model}.pth')

    
    print(f"Avg validation loss on epoch {epoch}: {np.array(val_loss) / len(val_dataloader)}")


