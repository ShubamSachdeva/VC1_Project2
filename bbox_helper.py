import numpy as np
import torch

''' Prior Bounding Box  ------------------------------------------------------------------------------------------------
'''


def generate_prior_bboxes(prior_layer_cfg):
    """
    Generate prior bounding boxes on different feature map level. This function used in 'cityscape_dataset.py'

    Use VGG_SSD 300x300 as example:
    Feature map dimension for each output layers:
       Layer    | Map Dim (h, w) | Single bbox size that covers in the original image
    1. Conv5    | (38x38)        | (30x30) (unit. pixels)
    2. Conv11    | (19x19)        | (60x60)
    3. Conv14_2  | (10x10)        | (111x111)
    4. Conv15_2  | (5x5)          | (162x162)
    5. Conv16_2 | (3x3)          | (213x213)
    6. Conv17_2 | (1x1)          | (264x264)

    NOTE: The setting may be different using MobileNet v3, you have to set your own implementation.
    Tip: see the reference: 'Choosing scales and aspect ratios for default boxes' in original paper page 5.
    :param prior_layer_cfg: configuration for each feature layer, see the 'example_prior_layer_cfg' in the following.
    :return prior bounding boxes with form of (cx, cy, w, h), where the value range are from 0 to 1, dim (1, num_priors, 4)
    """
    prior_layer_cfg = [
        # Example:
        {'layer_name': 'Conv5', 'feature_dim_hw': (38, 38), 'bbox_size': (30, 30), 'aspect_ratio': (1.0, 1 / 2, 1 / 3, 2.0, 3.0, '1t')},
        {'layer_name': 'Conv11', 'feature_dim_hw': (19, 19), 'bbox_size': (60, 60), 'aspect_ratio': (1.0, 1 / 2, 1 / 3, 2.0, 3.0, '1t')},
        {'layer_name': 'Conv14_2', 'feature_dim_hw': (10, 10), 'bbox_size': (111, 111), 'aspect_ratio': (1.0, 1 / 2, 1 / 3, 2.0, 3.0, '1t')},
        {'layer_name': 'Conv15_2', 'feature_dim_hw': (5, 5), 'bbox_size': (162, 162), 'aspect_ratio': (1.0, 1 / 2, 1 / 3, 2.0, 3.0, '1t')},
        {'layer_name': 'Conv16_2', 'feature_dim_hw': (3, 3), 'bbox_size': (213, 213), 'aspect_ratio': (1.0, 1 / 2, 1 / 3, 2.0, 3.0, '1t')},
        {'layer_name': 'Conv17_2', 'feature_dim_hw': (1, 1), 'bbox_size': (264, 264), 'aspect_ratio': (1.0, 1 / 2, 1 / 3, 2.0, 3.0, '1t')}
    ]
    sk_list = [0.1, 0.2, 0.37, 0.54, 0.71, 0.88, 1.05]

    priors_bboxes = []
    for feat_level_idx in range(0, len(prior_layer_cfg)):               # iterate each layers
        layer_cfg = prior_layer_cfg[feat_level_idx]
        layer_feature_dim = layer_cfg['feature_dim_hw']
        layer_aspect_ratio = layer_cfg['aspect_ratio']

        # Todo: compute S_{k} (reference: SSD Paper equation 4.)
        sk = sk_list[feat_level_idx]
        fk = layer_cfg['feature_dim_hw'][0]

        for y in range(0, layer_feature_dim[0]):
            for x in range(0,layer_feature_dim[0]):

                # Todo: compute bounding box center
                cx = (x+0.5)/fk
                cy = (y+0.5)/fk

                # Todo: generate prior bounding box with respect to the aspect ratio
                for aspect_ratio in layer_aspect_ratio:
                    if aspect_ratio == '1t':
                        sk_ = np.sqrt(sk_list[feat_level_idx] * sk_list[feat_level_idx+1])
                        aspect_ratio=1.0
                        h = sk_ / np.sqrt(aspect_ratio)
                        w = sk_ * np.sqrt(aspect_ratio)
                        priors_bboxes.append([cx, cy, w, h])
                    else:
                        h = sk/np.sqrt(aspect_ratio)
                        w = sk* np.sqrt(aspect_ratio)
                        priors_bboxes.append([cx, cy, w, h])
    # np.set_printoptions(threshold=np.inf)
    # print(np.asarray(priors_bboxes))
    # Convert to Tensor
    priors_bboxes = torch.tensor(priors_bboxes)
    priors_bboxes = torch.clamp(priors_bboxes, 0.0, 1.0)
    num_priors = priors_bboxes.shape[0]

    # [DEBUG] check the output shape
    assert priors_bboxes.dim() == 2
    assert priors_bboxes.shape[1] == 4
    return priors_bboxes


def iou(a: torch.Tensor, b: torch.Tensor):
    """
    # Compute the Intersection over Union
    Note: function iou(a, b) used in match_priors
    :param a: bounding boxes, dim: (n_items, 4)
    :param b: bounding boxes, dim: (n_items, 4) or (1, 4) if b is a reference
    :return: iou value: dim: (n_item)
    """
    # [DEBUG] Check if input is the desire shape
    assert a.dim() == 2
    assert a.shape[1] == 4
    assert b.dim() == 2
    assert b.shape[1] == 4
    a = center2corner(a)
    b = center2corner(b)
    a_area =(a[:,2]-a[:,0])*(a[:,3]-a[:,1])
    b_area = (b[:,2]-b[:,0])*(b[:,3]-b[:,1])
    x_max, y_max = np.maximum(a[:,0],b[:,0]), np.maximum(a[:,1], b[:,1])
    x_min, y_min = np.minimum(a[:,2],b[:,2]), np.maximum(a[:,3], b[:,3])
    temp_w = np.maximum((x_min-x_max),0)
    temp_h = np.maximum((y_min-y_max),0)
    a_and_b = temp_h*temp_w
    iou = a_and_b/(a_area+b_area-a_and_b)

    # [DEBUG] Check if output is the desire shape
    assert iou.dim() == 1
    assert iou.shape[0] == a.shape[0]
    return iou


def match_priors(prior_bboxes: torch.Tensor, gt_bboxes: torch.Tensor, gt_labels: torch.Tensor, iou_threshold: float):
    """
    Match the ground-truth boxes with the priors.
    Note: Use this function in your ''cityscape_dataset.py', see the SSD paper page 5 for reference. (note that default box = prior boxes)

    :param gt_bboxes: ground-truth bounding boxes, dim:(n_samples, 4)
    :param gt_labels: ground-truth classification labels, negative (background) = 0, dim: (n_samples)
    :param prior_bboxes: prior bounding boxes on different levels, dim:(num_priors, 4)
    :param iou_threshold: matching criterion
    :return matched_boxes: real matched bounding box, dim: (num_priors, 4)
    :return matched_labels: real matched classification label, dim: (num_priors)
    """
    # [DEBUG] Check if input is the desire shape
    assert gt_bboxes.dim() == 2
    assert gt_bboxes.shape[1] == 4
    assert gt_labels.dim() == 1
    assert gt_labels.shape[0] == gt_bboxes.shape[0]
    assert prior_bboxes.dim() == 2
    assert prior_bboxes.shape[1] == 4

    matched_boxes = None
    matched_labels = None

    # TODO: implement prior matching

    # [DEBUG] Check if output is the desire shape
    assert matched_boxes.dim() == 2
    assert matched_boxes.shape[1] == 4
    assert matched_labels.dim() == 1
    assert matched_labels.shape[0] == matched_boxes.shape[0]

    return matched_boxes, matched_labels


''' NMS ----------------------------------------------------------------------------------------------------------------
'''
def nms_bbox(bbox_loc, bbox_confid_scores, overlap_threshold=0.5, prob_threshold=0.6):
    """
    Non-maximum suppression for computing best overlapping bounding box for a object
    Use this function when testing the samples.

    :param bbox_loc: bounding box loc and size, dim: (num_priors, 4)
    :param bbox_confid_scores: bounding box confidence probabilities, dim: (num_priors, num_classes)
    :param overlap_threshold: the overlap threshold for filtering out outliers
    :return: selected bounding box with classes
    """

    # [DEBUG] Check if input is the desire shape
    assert bbox_loc.dim() == 2
    assert bbox_loc.shape[1] == 4
    assert bbox_confid_scores.dim() == 2
    assert bbox_confid_scores.shape[0] == bbox_loc.shape[0]

    sel_bbox = []

    # Todo: implement nms for filtering out the unnecessary bounding boxes
    num_classes = bbox_confid_scores.shape[1]
    for class_idx in range(0, num_classes):

        # Tip: use prob_threshold to set the prior that has higher scores and filter out the low score items for fast
        # computation

        pass

    return sel_bbox


''' Bounding Box Conversion --------------------------------------------------------------------------------------------
'''


def loc2bbox(loc, priors, center_var=0.1, size_var=0.2):
    """
    Compute SSD predicted locations to boxes(cx, cy, h, w).
    :param loc: predicted location, dim: (N, num_priors, 4)
    :param priors: default prior boxes, dim: (1, num_prior, 4)
    :param center_var: scale variance of the bounding box center point
    :param size_var: scale variance of the bounding box size
    :return: boxes: (cx, cy, h, w)
    """
    assert priors.shape[0] == 1
    assert priors.dim() == 3

    # prior bounding boxes
    p_center = priors[..., :2]
    p_size = priors[..., 2:]

    # locations
    l_center = loc[..., :2]
    l_size = loc[..., 2:]

    # real bounding box
    return torch.cat([
        center_var * l_center * p_size + p_center,      # b_{center}
        p_size * torch. exp(size_var * l_size)           # b_{size}
    ], dim=-1)


def bbox2loc(bbox, priors, center_var=0.1, size_var=0.2):
    """
    Compute boxes (cx, cy, h, w) to SSD locations form.
    :param bbox: bounding box (cx, cy, h, w) , dim: (N, num_priors, 4)
    :param priors: default prior boxes, dim: (1, num_prior, 4)
    :param center_var: scale variance of the bounding box center point
    :param size_var: scale variance of the bounding box size
    :return: loc: (cx, cy, h, w)
    """
    assert priors.shape[0] == 1
    assert priors.dim() == 3

    # prior bounding boxes
    p_center = priors[..., :2]
    p_size = priors[..., 2:]

    # locations
    b_center = bbox[..., :2]
    b_size = bbox[..., 2:]

    return torch.cat([
        1 / center_var * ((b_center - p_center) / p_size),
        torch.log(b_size / p_size) / size_var
    ], dim=-1)


def center2corner(center):
    """
    Convert bounding box in center form (cx, cy, w, h) to corner form (x,y) (x+w, y+h)
    :param center: bounding box in center form (cx, cy, w, h)
    :return: bounding box in corner form (x,y) (x+w, y+h)
    """
    return torch.cat([center[..., :2] - center[..., 2:]/2,
                      center[..., :2] + center[..., 2:]/2], dim=-1)


def corner2center(corner):
    """
    Convert bounding box in center form (cx, cy, w, h) to corner form (x,y) (x+w, y+h)
    :param center: bounding box in center form (cx, cy, w, h)
    :return: bounding box in corner form (x,y) (x+w, y+h)
    """
    return torch.cat([corner[..., :2] - corner[..., 2:]/2,
                      corner[..., :2] + corner[..., 2:]/2], dim=-1)