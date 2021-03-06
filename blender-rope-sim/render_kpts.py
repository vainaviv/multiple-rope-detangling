import bpy
import numpy as np
import xml.etree.cElementTree as ET
from xml.dom import minidom

from math import pi
import os
import sys
sys.path.append(os.getcwd())

from rigidbody_rope import *
from sklearn.neighbors import NearestNeighbors
from knots import tie_pretzel_knot, tie_stevedore, tie_figure_eight, tie_double_pretzel, flip_pretzel_knot, flip_figure_eight
from untangle_utils import *
from dr_utils import *

def set_animation_settings(anim_end):
    # Sets up the animation to run till frame anim_end (otherwise default terminates @ 250)
    scene = bpy.context.scene
    scene.frame_end = anim_end
    scene.rigidbody_world.point_cache.frame_end = anim_end

def set_render_settings(engine, render_size):
    # Set rendering engine, dimensions, colorspace, images settings
    if os.path.exists("./render_kpts_output"):
        os.system('rm -r ./render_kpts_output')
    os.makedirs('./render_kpts_output')

    if os.path.exists("./render_kpts_output/images"):
        os.system('rm -r ./render_kpts_output/images')
    os.makedirs('./render_kpts_output/images')

    if os.path.exists("./render_kpts_output/keypoints"):
        os.system('rm -r ./render_kpts_output/keypoints')
    os.makedirs('./render_kpts_output/keypoints')
 
    if os.path.exists('./render_kpts_output/image_masks'):
        os.system('rm -r ./render_kpts_output/image_masks')
    os.makedirs('./render_kpts_output/image_masks')

    if os.path.exists('./render_kpts_output/image_depths'):
        os.system('rm -r ./render_kpts_output/image_depths')
    os.makedirs('./render_kpts_output/image_depths')

    if os.path.exists('./render_kpts_output/black_out_pixels'):
        os.system('rm -r ./render_kpts_output/black_out_pixels')
    os.makedirs('./render_kpts_output/black_out_pixels')

    scene = bpy.context.scene
    scene.render.engine = engine
    render_width, render_height = render_size
    scene.render.resolution_x = render_width
    scene.render.resolution_y = render_height
    # DELETE
    #scene.view_settings.exposure = 3
    if engine == 'BLENDER_WORKBENCH':
        #scene.render.display_mode
        scene.render.image_settings.color_mode = 'RGB'
        scene.display_settings.display_device = 'None'
        scene.sequencer_colorspace_settings.name = 'XYZ'
        scene.render.image_settings.file_format='JPEG'
    elif engine == "BLENDER_EEVEE":
        scene.eevee.taa_samples = 1
        scene.render.image_settings.file_format='JPEG'
        scene.view_settings.view_transform = 'Raw'
        scene.eevee.taa_render_samples = 1

def save_kpts(annotation_idx, idx, annotation_list):
    np_annotations = np.array(annotation_list)
    np.save('./render_kpts_output/keypoints/%05d_%01d.npy'%(annotation_idx,idx), np_annotations)

def save_black_out_pixels(annotation_idx, idx, annotation_hold):
    np_annotations = np.array(annotation_hold)
    np.save('./render_kpts_output/black_out_pixels/%05d_%01d.npy'%(annotation_idx,idx), np_annotations)

def find_knot(num_segments, chain=False, depth_thresh=0.4, idx_thresh=3, pull_offset=2):

    piece = "Torus" if chain else "Cylinder"
    cache = {}

    # Make a single pass, store the xy positions of the cylinders
    for i in range(num_segments):
        cyl = get_piece(piece, i if i else -1)
        x,y,z = cyl.matrix_world.translation
        key = tuple((x,y))
        val = {"idx":i, "depth":z}
        cache[key] = val
    neigh = NearestNeighbors(2, 0)
    planar_coords = list(cache.keys())
    neigh.fit(planar_coords)
    # Now traverse and look for the under crossing
    for i in range(num_segments):
        cyl = get_piece(piece, i if i else -1)
        x,y,z = cyl.matrix_world.translation
        match_idxs = neigh.kneighbors([(x,y)], 2, return_distance=False) # 1st neighbor is always identical, we want 2nd
        nearest = match_idxs.squeeze().tolist()[1:][0]
        x1,y1 = planar_coords[nearest]
        curr_cyl, match_cyl = cache[(x,y)], cache[(x1,y1)]
        depth_diff = match_cyl["depth"] - curr_cyl["depth"]
        idx_diff = abs(match_cyl["idx"] - curr_cyl["idx"])
        if depth_diff > depth_thresh and idx_diff > idx_thresh:
            pull_idx = i + pull_offset # Pick a point slightly past under crossing to do the pull
            dx = planar_coords[pull_idx][0] - x
            dy = planar_coords[pull_idx][1] - y
            hold_idx = match_cyl["idx"]
            SCALE_X = 1
            SCALE_Y = 1
            Z_OFF = 2
            action_vec = [SCALE_X*dx, SCALE_Y*dy, Z_OFF] # Pull in the direction of the rope (NOTE: 7 is an arbitrary scale for now, 6 is z offset)
            return pull_idx, hold_idx, action_vec # Found! Return the pull, hold, and action
    return 16, 25, [0,0,0] # Didn't find a pull/hold
    #return -1, -1, [0,0,0] # Didn't find a pull/hold

def annotate(frame, offset=4, num_knots=1):
    global last
    # knot_only = True:  means only record the under, over crossings
    # knot_only = False:  means record annotations for full rope
    '''Gets num_annotations annotations of cloth image at provided frame #, adds to mapping'''
    scene = bpy.context.scene
    render_size = (
            int(scene.render.resolution_x),
            int(scene.render.resolution_y),
            )
    annot_list = []
    pull_idx, hold_idx, _ = find_knot(last)
    indices = [0, pull_idx, hold_idx, last-1]
    #indices = [pull_idx, hold_idx]
    #indices = [0, last-1]
    annotations = [] # [[x1,y1],[x2,y2],...
    for i in indices:
        #(x,y) = cyl_to_pixels([i])[0][0]
        cyl = get_piece("Cylinder", i)
        camera_coord = bpy_extras.object_utils.world_to_camera_view(scene, bpy.context.scene.camera, cyl.matrix_world.translation)
        x, y = [round(camera_coord.x * render_size[0]), round(render_size[1] - camera_coord.y * render_size[1])]
        j = i
        while not(x<render_size[0] and x>0 and y<render_size[1] and y>0):
            if j<last//2:
                j += 1
            else:
                j -= 1
            cyl = get_piece("Cylinder", j)
            camera_coord = bpy_extras.object_utils.world_to_camera_view(scene, bpy.context.scene.camera, cyl.matrix_world.translation)
            x, y = [round(camera_coord.x * render_size[0]), round(render_size[1] - camera_coord.y * render_size[1])]
        annotations.append([x,y])
        
    save_kpts(frame, 0, annotations)

def annotate_multiple_black_out(frame, offset=4, num_knots=1):
    #TODO
    pull_idx_actual, hold_idx_actual, _ = find_knot(last) 
    knot_point_min = min(pull_idx_actual, hold_idx_actual)
    knot_point_max = max(pull_idx_actual, hold_idx_actual)
    annotations = []

    # generate a random amount of blackout locations
    for j in range(3):
        if j == 0: #no blackouts at all
            save_black_out_pixels(frame, 0, [[0,0]])
            hold_idx = hold_idx_actual
            pull_idx = pull_idx_actual
            indices = [0, pull_idx, hold_idx, last-1]
            annotations = calculate_x_y_pixels(indices)
            save_kpts(frame, j, annotations)
            continue
        if j == 1: #possinle blackout before knot point
            num_dropouts = np.random.randint(2, high = 10)
            cylinders_to_drop = np.random.randint(0, 50, num_dropouts)
        if j == 2: #black out only after knot point
            num_dropouts = np.random.randint(2, high = 10)
            cylinders_to_drop = np.random.randint(knot_point_max + 1, 50, num_dropouts) #make this maximum not minimum
        # reorder them in numerical order
        cylinders_to_drop = np.sort(cylinders_to_drop)
        print(cylinders_to_drop)
        # pick the smallest capsule index and check where it is relative to the knot_point
        right_most_cyl = cylinders_to_drop[0]
        # if equal disregard this point and pick the next smallest
        if right_most_cyl == knot_point_min or right_most_cyl == knot_point_max:
            cylinders_to_drop = cylinders_to_drop[1:]
            right_most_cyl = cylinders_to_drop[0]
        # if less than, save black out pixels with updated pull and hold
        if right_most_cyl < knot_point_min:
            hold_idx = right_most_cyl
            pull_idx = hold_idx + 2
        # if greater than, save black out pixels with original pull and hold
        elif right_most_cyl > knot_point_max:
            hold_idx = hold_idx_actual
            pull_idx = pull_idx_actual

        save_black_out_pixels(frame, j, calculate_x_y_pixels(cylinders_to_drop))
        indices = [0, pull_idx, hold_idx, last-1]
        annotations = calculate_x_y_pixels(indices)
        save_kpts(frame, j, annotations)


def annotate_black_out_knot(frame, offset=4, num_knots=1): #one blackout at a time
    pull_idx_actual, hold_idx_actual, _ = find_knot(last) 
    knot_point = min(pull_idx_actual, hold_idx_actual)
    annotations = []

    for j in range(3): 
        if j==1:
            #move to a point before the knot so update pull and hold
            if (0 >= knot_point-1):
                hold_idx = 0
            else:
                hold_idx = random.randint(0,knot_point-1)
            pull_idx = hold_idx + 2
        else:
            #move to a point after the knot so no need to update pull and hold
            hold_idx = hold_idx_actual
            pull_idx = pull_idx_actual

        indices = [0, pull_idx, hold_idx, last-1]
        annotations = calculate_x_y_pixels(indices)
        if j==1: #early crossing and hold pixel
            indices = [hold_idx]
            save_black_out_pixels(frame, 1, calculate_x_y_pixels(indices))
        elif j==0: #no crossing
            save_black_out_pixels(frame, 0, [[0,0]])
        elif j==2: #crossing after
            if (knot_point+1) == 48:
                hold_idx = 48
            else:
                hold_idx = random.randint(knot_point+1, 48)
            if hold_idx == pull_idx_actual:
                if (pull_idx_actual + 1) == 48:
                    hold_idx = 48
                else:
                    hold_idx = random.randint(pull_idx_actual+1, 48)
            indices = [hold_idx]
            save_black_out_pixels(frame, 2, calculate_x_y_pixels(indices))

        save_kpts(frame, j, annotations)

def calculate_x_y_pixels(indices):
    scene = bpy.context.scene
    render_size = (
            int(scene.render.resolution_x),
            int(scene.render.resolution_y),
            )
    annotations = [] # [[x1,y1],[x2,y2],...
    for i in indices:
        #(x,y) = cyl_to_pixels([i])[0][0]
        cyl = get_piece("Cylinder", i)
        camera_coord = bpy_extras.object_utils.world_to_camera_view(scene, bpy.context.scene.camera, cyl.matrix_world.translation)
        x, y = [round(camera_coord.x * render_size[0]), round(render_size[1] - camera_coord.y * render_size[1])]
        j = i
        while not(x<render_size[0] and x>0 and y<render_size[1] and y>0):
            if j<last//2:
                j += 1
            else:
                j -= 1
            cyl = get_piece("Cylinder", j)
            camera_coord = bpy_extras.object_utils.world_to_camera_view(scene, bpy.context.scene.camera, cyl.matrix_world.translation)
            x, y = [round(camera_coord.x * render_size[0]), round(render_size[1] - camera_coord.y * render_size[1])]
        annotations.append([x,y])
    return annotations


def get_piece(piece_name, piece_id):
    # Returns the piece with name piece_name, index piece_id
    if piece_id == -1 or piece_id == 0:
        return bpy.data.objects['%s' % (piece_name)]
    return bpy.data.objects['%s.%03d' % (piece_name, piece_id)]

def toggle_animation(obj, frame, animate):
    # Sets the obj to be animable or non-animable at particular frame
    obj.rigid_body.kinematic = animate
    obj.keyframe_insert(data_path="rigid_body.kinematic", frame=frame)

def take_action(obj, frame, action_vec, animate=True):
    # Keyframes a displacement for obj given by action_vec at given frame
    curr_frame = bpy.context.scene.frame_current
    dx,dy,dz = action_vec
    if animate != obj.rigid_body.kinematic:
        # We are "picking up" a dropped object, so we need its updated location
        obj.location = obj.matrix_world.translation
        obj.rotation_euler = obj.matrix_world.to_euler()
        obj.keyframe_insert(data_path="location", frame=curr_frame)
        obj.keyframe_insert(data_path="rotation_euler", frame=curr_frame)
    toggle_animation(obj, curr_frame, animate)
    obj.location += Vector((dx,dy,dz))
    obj.keyframe_insert(data_path="location", frame=frame)

def randomize_camera():
    #ANGLE_DIVS = 65
    ANGLE_DIVS = 58
    xrot = 0 #np.random.uniform(-pi/ANGLE_DIVS, pi/ANGLE_DIVS) 
    yrot = 0 #np.random.uniform(-pi/ANGLE_DIVS, pi/ANGLE_DIVS) 
    zrot = np.random.uniform(-pi/6, pi/6) 
    xoffset = 2
    yoffset = 2
    zoffset = 2
    dx = np.random.uniform(-xoffset, xoffset)
    dy = np.random.uniform(-yoffset, yoffset)
    dz = np.random.uniform(-zoffset, zoffset)
    bpy.context.scene.camera.rotation_euler = (xrot, yrot, zrot)
    piece = "Cylinder"
    mid_rope = get_piece(piece, 25)
    x,y,z = mid_rope.matrix_world.translation
    #bpy.context.scene.camera.location = Vector((x,y,np.random.uniform(15,25))) + Vector((dx, dy, dz))
    #bpy.context.scene.camera.location = Vector((x,y,np.random.uniform(15,25))) + Vector((dx, dy, dz))
    #bpy.context.scene.camera.location = Vector((x,y,np.random.uniform(13,24))) + Vector((dx, dy, dz))
    bpy.context.scene.camera.location = Vector((x,y,np.random.uniform(16,23))) + Vector((dx, dy, dz))

    #bpy.context.scene.camera.location = Vector((2,0,25)) + Vector((dx, dy, dz))
    
def render_frame(frame, render_offset=0, step=10, filename="%05d_%01d.jpg", folder="render_kpts_output/images", annot=True, num_knots=1, mapping=None):
    # DOMAIN RANDOMIZE
    global rig
    randomize_camera()
    #randomize_rig(rig, mode="braid")
    randomize_rig(rig)
    randomize_light()

    table = bpy.data.objects["Plane"]
    #color_randomize(table, color_range=(1,1))
    #color_randomize(rig, color_range=(0.4,0.4))
    if random.random() < 0.0:
        texture_randomize(table, 'dr_data/val2017')
    #elif random.random() < 0.66:
    #    texture_randomize(table, 'dr_data/background')
    else:
        #texture_randomize(table, 'dr_data/dark_val2017')
        texture_randomize(table, 'dr_data/val2017')
    if random.random() < 0.5:
        color_randomize(rig, color_range=(0.2,1)) #rig is rope, table is background
        # texture_randomize(rig, 'dr_data/red_rope_textures')
    else:
        texture_randomize(rig, 'dr_data/stripes')
        #texture_randomize(rig, 'dr_data/blue_rope_textures')

    # Renders a single frame in a sequence (if frame%step == 0)
    frame -= render_offset
    if frame%step == 0:
        for i in range(3):
            scene = bpy.context.scene
            index = frame//step
            # render_mask("image_masks/%06d_visible_mask.png", "images_depth/%06d_rgb.png", index)
            scene.render.filepath = os.path.join(folder, filename) % (index, i)
            bpy.ops.render.render(write_still=True)
        if annot:
            #annotate(index) 
            #annotate_black_out_knot(index)
            annotate_multiple_black_out(index)

def render_mask(frame, render_offset=0, step=10, mask_filename="%05d.jpg", depth_filename="%05d.jpg", folder_mask="render_kpts_output/image_masks", folder_depth="render_kpts_output/image_depths"):
    # NOTE: this method is still in progress
    scene = bpy.context.scene
    saved = scene.render.engine
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_samples = 1
    scene.eevee.taa_render_samples = 1
    scene.use_nodes = True
    tree = bpy.context.scene.node_tree
    links = tree.links
    render_node = tree.nodes["Render Layers"]
    norm_node = tree.nodes.new(type="CompositorNodeNormalize")
    inv_node = tree.nodes.new(type="CompositorNodeInvert")
    math_node = tree.nodes.new(type="CompositorNodeMath")
    math_node.operation = 'CEIL' # Threshold the depth image
    composite = tree.nodes.new(type = "CompositorNodeComposite")

    links.new(render_node.outputs["Depth"], inv_node.inputs["Color"])
    links.new(inv_node.outputs[0], norm_node.inputs[0])
    links.new(norm_node.outputs[0], composite.inputs["Image"])

    frame -= render_offset
    if frame%step == 0:
        scene = bpy.context.scene
        index = frame//step

        scene.render.filepath = os.path.join(folder_depth, depth_filename) % index
        bpy.ops.render.render(write_still=True)

        links.new(norm_node.outputs[0], math_node.inputs[0])
        links.new(math_node.outputs[0], composite.inputs["Image"])

        scene.render.filepath = os.path.join(folder_mask, mask_filename) % index
        bpy.ops.render.render(write_still=True)
    # Clean up 
    scene.render.engine = saved
    for node in tree.nodes:
        if node.name != "Render Layers":
            tree.nodes.remove(node)
    scene.use_nodes = False


def reidemeister(params, start_frame, render=False, render_offset=0, annot=True, num_knots=1, mapping=None):

    piece = "Cylinder"
    last = params["num_segments"]-1
    end1 = get_piece(piece, -1)
    end2 = get_piece(piece, last)

    middle_frame = start_frame+50
    end_frame = start_frame+100

    take_action(end1, middle_frame, (np.random.uniform(9,11)-end1.matrix_world.translation[0],np.random.uniform(-3,3),0))
    for step in range(start_frame, middle_frame):
        bpy.context.scene.frame_set(step)
        if render:
            render_frame(step, render_offset=render_offset, annot=annot, mapping=mapping, num_knots=num_knots)
            render_mask(step, render_offset=render_offset)
    take_action(end2, end_frame, (np.random.uniform(-6,-8)-end2.matrix_world.translation[0],np.random.uniform(-3,3),0))
    # Drop the ends

    toggle_animation(end1, middle_frame, False)
    #toggle_animation(end1, end_frame, False)
    toggle_animation(end2, end_frame, False)

    for step in range(middle_frame, end_frame):
        bpy.context.scene.frame_set(step)
        if render:
            render_frame(step, render_offset=render_offset, annot=annot, mapping=mapping, num_knots=num_knots)
            render_mask(step, render_offset=render_offset)
    return end_frame

def take_undo_action_oracle(params, start_frame, render=False, render_offset=0, annot=True, num_knots=1, mapping=None):
    global last
    piece = "Cylinder"
    pull_idx, hold_idx, action_vec = find_knot(last)
    action_vec = np.array(action_vec) + np.random.uniform(-0.75, 0.75, 3)
    #action_vec = np.array(action_vec) + np.random.uniform(-1,1,3)
    action_vec /= np.linalg.norm(action_vec)
    #action_vec *= 2.5
    #action_vec *= 2.8
    action_vec *= 3
    action_vec[2] = 0.8
    pull_cyl = get_piece(piece, pull_idx if pull_idx else -1)
    hold_cyl = get_piece(piece, hold_idx if hold_idx else -1)
    end_frame = start_frame + 150
    take_action(hold_cyl, end_frame, (0,0,0))

    for step in range(start_frame, start_frame + 10):
        bpy.context.scene.frame_set(step)
        if render and (abs(step-start_frame) < 5 or abs(step-(start_frame+10)) < 5):
            render_frame(step, render_offset=render_offset, annot=annot, mapping=mapping)
            render_mask(step, render_offset=render_offset)
        elif render:
            render_offset += 1

    take_action(pull_cyl, end_frame, action_vec)
    ## Release both pull, hold
    toggle_animation(pull_cyl, end_frame, False)
    toggle_animation(hold_cyl, end_frame, False)
    settle_time = 30

    for step in range(start_frame + 10, end_frame+settle_time):
        bpy.context.scene.frame_set(step)
        if render and (abs(step-(start_frame+10)) < 2 or abs(step-(end_frame+settle_time)) < 2):
            render_frame(step, render_offset=render_offset, annot=annot, mapping=mapping)
            render_mask(step, render_offset=render_offset)
        elif render:
            render_offset += 1
    return end_frame+settle_time, render_offset
 
def take_random_action(params, start_frame, render=False, render_offset=0, annot=True):
    global last
    piece = "Cylinder"
    #pull_idx = random.choice(range(last//2 - 5, last//2 + 5))
    #action_vec = np.random.uniform(-2, 2, 3)
    pull_idx = 18
    dx = np.random.uniform(-1,-2)
    dy = np.random.uniform(0,2)
    action_vec = [dx,dy,2]
    action_vec[2] = np.random.uniform(1,1.5)
    pull_cyl = get_piece(piece, pull_idx if pull_idx else -1)
    end_frame = start_frame + 100
    settle_time = 10
    take_action(pull_cyl, end_frame, action_vec)
    toggle_animation(pull_cyl, end_frame, False)
    for step in range(start_frame, end_frame+settle_time):
        bpy.context.scene.frame_set(step)
        render_frame(step, render_offset=render_offset, annot=annot, mapping=None)
        render_mask(step, render_offset=render_offset)
    return end_frame+settle_time, render_offset

def generate_dataset(iters, params, chain=False, render=False):

    #set_animation_settings(15000)
    set_animation_settings(5000)
    piece = "Cylinder"
    last = params["num_segments"]-1
    mapping = None

    render_offset = 0
    num_loosens = 5
    for i in range(iters):
        print("Iter %d of %d" % (i,iters))
        num_knots = 1
        if i%3==0:
            #knot_end_frame = tie_pretzel_knot(params, render=False)
            knot_end_frame = flip_pretzel_knot(params, render=False)
        elif i%3==1:
            #knot_end_frame = tie_figure_eight(params, render=False)
            knot_end_frame = flip_figure_eight(params, render=False)
        else:
            knot_end_frame = tie_double_pretzel(params, render=False)
        knot_end_frame = perturb_knot(params, knot_end_frame)
        render_offset += knot_end_frame
        reid_end_frame = reidemeister(params, knot_end_frame, render=render, render_offset=render_offset, num_knots=num_knots, mapping=mapping)
        perturb_end_frame = random_perturb(reid_end_frame, params, render=False)
        render_offset += perturb_end_frame - reid_end_frame
        start = perturb_end_frame
        for i in range(num_loosens):
            loosen_end_frame, offset = take_undo_action_oracle(params, start, render=render, render_offset=render_offset, num_knots=num_knots, mapping=mapping)
            #    loosen_end_frame, offset = take_random_action(params, start, render=render, render_offset=render_offset)
            start = loosen_end_frame
            render_offset = offset
        render_offset -= loosen_end_frame
        bpy.context.scene.frame_set(0)
        for a in bpy.data.actions:
            bpy.data.actions.remove(a)

if __name__ == '__main__':
    with open("rigidbody_params.json", "r") as f:
        params = json.load(f)
    last = params["num_segments"]
    clear_scene()
    make_capsule_rope(params)
    #make_capsule_rope_stiff(params)
    rig = rig_rope(params, mode="cable")
    #rig = rig_rope(params, braid=0)
    #rig = rig_rope(params, braid=1)
    add_camera_light()
    set_render_settings(params["engine"],(params["render_width"],params["render_height"]))
    make_table(params)
    start = time.time()
    iters = 90 #15
    generate_dataset(iters, params, render=True)
    end = time.time()
    print("time", end-start)
