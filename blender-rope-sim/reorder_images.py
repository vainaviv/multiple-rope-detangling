import cv2
import os
import argparse
import json
import numpy as np

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--dir', type=str, default='./real_images/no_mask/hulk_two_rope_test')
    args = parser.parse_args()
    reordered_folder = args.dir + '_reordered'
    print(reordered_folder)
    if os.path.exists(reordered_folder):
        remove_command = 'rm -r ' + reordered_folder
        os.system(remove_command)
    os.mkdir(reordered_folder)
# 
    i = 0
    # dir_len = len(os.listdir('train_sets/multiple_blackout/train/blacked_out'))
    # for j in range(len(os.listdir(args.dir))):
    #     f = "%05d.png"%(j)
    for f in os.listdir(args.dir):
        print(f)
        save_img_filename = "%05d.png"%(i)
        print("Relabeling " + save_img_filename)
        img = cv2.imread('%s/%s'%(args.dir, f)).copy()
        cv2.imwrite('./real_images/no_mask/hulk_two_rope_test_reordered/%s'%(save_img_filename), img)
        i += 1
