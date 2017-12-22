import numpy as np

from chainer import cuda

from modules.loc2bbox import loc2bbox
from modules.non_maximum_suppression import \
    non_maximum_suppression


class ProposalCreator(object):
    """Proposal regions are generated by calling this object.

    The :meth:`__call__` of this object outputs object detection proposals by
    applying estimated bounding box offsets
    to a set of anchors.

    This class takes parameters to control number of bounding boxes to
    pass to NMS and keep after NMS.
    If the paramters are negative, it uses all the bounding boxes supplied
    or keep all the bounding boxes returned by NMS.

    Args:
        nms_thresh (float): Threshold value used when calling NMS.
        n_train_pre_nms (int): Number of top scored bounding boxes
            to keep before passing to NMS in train mode.
        n_train_post_nms (int): Number of top scored bounding boxes
            to keep after passing to NMS in train mode.
        n_test_pre_nms (int): Number of top scored bounding boxes
            to keep before passing to NMS in test mode.
        n_test_post_nms (int): Number of top scored bounding boxes
            to keep after passing to NMS in test mode.
        force_cpu_nms (bool): If this is :obj:`True`,
            always use NMS in CPU mode. If :obj:`False`,
            the NMS mode is selected based on the type of inputs.
        min_size (int): A paramter to determine the threshold on
            discarding bounding boxes based on their sizes.

    """

    def __init__(self,
                 nms_thresh=0.7,
                 n_train_pre_nms=24000,
                 n_train_post_nms=2000,
                 n_test_pre_nms=12000,
                 n_test_post_nms=300,
                 force_cpu_nms=False,
                 min_size=16
                 ):

        self.nms_thresh = nms_thresh
        self.n_train_pre_nms = n_train_pre_nms
        self.n_train_post_nms = n_train_post_nms
        self.n_test_pre_nms = n_test_pre_nms
        self.n_test_post_nms = n_test_post_nms
        self.force_cpu_nms = force_cpu_nms
        self.min_size = min_size

    def __call__(self, loc, score,
                 anchor, img_size, scale=1., test=True):
        """Propose RoIs.

        Inputs :obj:`loc, score, anchor` refer to the same anchor when indexed
        by the same index.

        On notations, :math:`R` is the total number of anchors. This is equal
        to product of the height and the width of an image and the number of
        anchor bases per pixel.

        Type of the output is same as the inputs.

        Args:
            loc (array): Predicted offsets and scaling to anchors.
                Its shape is :math:`(R, 4)`.
            score (array): Predicted foreground probability for anchors.
                Its shape is :math:`(R,)`.
            anchor (array): Coordinates of anchors. Its shape is
                :math:`(R, 4)`.
            img_size (tuple of ints): A tuple :obj:`width, height`,
                which contains image size after scaling.
            scale (float): The scaling factor used to scale an image after
                reading it from a file.
            test (bool): Execute in test mode or not.
                Default value is :obj:`True`.

        Returns:
            array:
            An array of coordinates of proposal boxes.
            Its shape is :math:`(S, 4)`. :math:`S` is less than
            :obj:`self.n_test_post_nms` in test time and less than
            :obj:`self.n_train_post_nms` in train time. :math:`S` depends on
            the size of the predicted bounding boxes and the number of
            bounding boxes discarded by NMS.

        """
        n_pre_nms = self.n_test_pre_nms if test else self.n_train_pre_nms
        n_post_nms = self.n_test_post_nms if test else self.n_train_post_nms

        xp = cuda.get_array_module(loc)
        loc = cuda.to_cpu(loc)
        score = cuda.to_cpu(score)
        anchor = cuda.to_cpu(anchor)

        # Convert anchors into proposal via bbox transformations.
        roi = loc2bbox(anchor, loc)

        min_size = self.min_size * scale
        w_minimum_bound = roi[:, 2] * xp.abs(xp.cos(roi[:, 4])) + roi[:, 3] * xp.abs(xp.sin(roi[:, 4]))
        h_minimum_bound = roi[:, 2] * xp.abs(xp.sin(roi[:, 4])) + roi[:, 3] * xp.abs(xp.cos(roi[:, 4]))
        keep = xp.where((roi[:, 2] >= min_size) & (roi[:, 3] >= min_size) & (roi[:, 0] - w_minimum_bound/2 > 0) & (
            roi[:, 0] + w_minimum_bound/2 < img_size[0]) & (roi[:, 1] - h_minimum_bound/2 > 0) & (
                            roi[:, 1] + h_minimum_bound/2 < img_size[1]))[0]
        roi = roi[keep, :]
        score = score[keep]

        # Sort all (proposal, score) pairs by score from highest to lowest.
        # Take top pre_nms_topN (e.g. 6000).
        order = score.ravel().argsort()[::-1]
        if n_pre_nms > 0:
            order = order[:n_pre_nms]
        roi = roi[order, :]
        score = score[order]

        # Apply nms (e.g. threshold = 0.7).
        # Take after_nms_topN (e.g. 300).
        # if xp != np and not self.force_cpu_nms:
        #     keep = non_maximum_suppression(
        #         cuda.to_gpu(roi),
        #         thresh=self.nms_thresh)
        #     keep = cuda.to_cpu(keep)
        # else:
        #     keep = non_maximum_suppression(
        #         roi,
        #         thresh=self.nms_thresh)
        # if n_post_nms > 0:
        #     keep = keep[:n_post_nms]
        # roi = roi[keep]

        if xp != np:
            roi = cuda.to_gpu(roi)
        return roi
