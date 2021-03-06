import torch
import torchvision
import torch.nn as nn
import torch.nn.functional as F
import time
import sys
sys.path.insert(0, '/host/src')
from resnet_dilated_multi import Resnet34_8s

class KeypointsGauss(nn.Module):
	def __init__(self, num_keypoints, img_height=480, img_width=640, num_classes=3):
		super(KeypointsGauss, self).__init__()
		self.num_keypoints = num_keypoints
		self.num_classes = num_classes
		self.num_outputs = self.num_keypoints
		self.img_height = img_height
		self.img_width = img_width
		self.resnet = Resnet34_8s()
		self.sigmoid = torch.nn.Sigmoid()
	def forward(self, x):
		heatmap, cls = self.resnet(x) 
		heatmaps = self.sigmoid(heatmap[:,:self.num_keypoints, :, :])
		return heatmaps, cls

if __name__ == '__main__':
	model = KeypointsGauss(4).cuda()
	x = torch.rand((1,3,480,640)).cuda()
	heatmaps, class_scores = model.forward(x)
	print(x.shape)
	print(heatmaps.shape)
	print(class_scores.shape)
