"""dependencies.

app/dependencies.py

"""

from typing import List, Callable

import cv2
import numpy as np
import os

from titiler.core.algorithm import BaseAlgorithm
from rio_tiler.models import ImageData
from rio_tiler.io import Reader
from rasterio import windows

from titiler.core.algorithm import algorithms as default_algorithms
from titiler.core.algorithm import Algorithms
import walrus

db = walrus.Database(
    host=os.getenv("REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", 6379))
)
cache = db.cache()
CACHE_TIMEOUT = int(os.getenv("BBOX_CACHE_TIMEOUT", 60))
BBOX_SCALE = int(os.getenv("BBOX_SCALE", 6))


class StravaHeatmap(BaseAlgorithm):
    '''
    requires that the layer sets the buffer parameter &buffer=x
    '''
    input_nbands: int = 1
    output_nbands: int = 1
    output_dtype: str = "uint8"

    buffer: int = 512
    tilesize: int = 256

    def __call__(self, img: ImageData) -> ImageData:
        stats = img.statistics()
        bs = stats.get('b1')
        bstats = (bs.min, bs.max)
        
        img.rescale(
            in_range=(bstats,),
            out_range=((0, 255),)
        )
        eq_img = cv2.equalizeHist(img.data_as_image())
        bounds = windows.bounds(windows.Window(self.tilesize, self.tilesize, self.tilesize, self.tilesize), img.transform)
        img = img.clip(bounds)
        return ImageData(
            eq_img[self.buffer:self.buffer+self.tilesize, self.buffer:self.buffer+self.tilesize],
            assets=img.assets,
            crs=img.crs,
            bounds=img.bounds,
        )

class StravaCLAHE(BaseAlgorithm):
    '''
    requires that the layer sets the buffer parameter &buffer=x
    '''
    input_nbands: int = 1
    output_nbands: int = 1
    output_dtype: str = "uint8"

    buffer: int = 512
    tilesize: int = 256
    def __call__(self, img: ImageData) -> ImageData:
        data = img.data_as_image()
        data = cv2.normalize(src=data, dst=None, alpha=0, beta=2**8, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        clahe = cv2.createCLAHE(clipLimit=1, tileGridSize=(3, 3))
        eq_img = clahe.apply(data)
        pos_start, pos_end = self.buffer, self.buffer+self.tilesize
        cut_img = eq_img[pos_start:pos_end, pos_start:pos_end]

        # compute the mask, find all the nan values
        mask = (np.isnan(img.data))[0][pos_start:pos_end, pos_start:pos_end]
        # generate a new image applying the mask and zero-ing all the masked pixel
        data = np.where(~mask, cut_img, 0)
        # generate an array mask, with 0 and 255
        modified_mask = np.where(mask, 255, 0)
        # apply the mask over multiple bands
        if img.data.shape[0] > 1:
            modified_mask = np.repeat(modified_mask[None, :, :], img.data.shape[0], axis=0)

        masked_array = np.ma.MaskedArray(data, mask=modified_mask)
        return ImageData(
            masked_array,
            assets=img.assets,
            crs=img.crs,
            bounds=img.bounds,
        )


@cache.cached(timeout=CACHE_TIMEOUT)
def get_stats_by_bbox(url, bbox):
    with Reader(url) as dst:
        cov = dst.part(bbox)
        cov_stats = cov.statistics()
        bs = cov_stats.get('b1')
        return ((bs.min, bs.max),)


class BBoxStats(BaseAlgorithm):
    input_nbands: int = 1
    output_nbands: int = 1
    output_dtype: str = "uint8"

    bbox: List[float]
    scale: int = 1

    def __call__(self, img: ImageData) -> ImageData:
        # compute the mask, find all the nan values
        mask = np.isnan(img.data)[0]
        # generate an array mask, with 0 and 255
        modified_mask = np.where(mask, 255, 0)
        
        if self.scale > BBOX_SCALE:
            stats = get_stats_by_bbox(img.assets[0], self.bbox)
        else:
            stats = img.dataset_statistics

        img.rescale(
            in_range=stats,
            out_range=((0, 255),)
        )
        data = np.where(~mask, img.data, 0)
        masked_array = np.ma.MaskedArray(data, mask=modified_mask)

        return ImageData(
            masked_array,
            assets=img.assets,
            crs=img.crs,
            bounds=img.bounds,
        ) 


class MaskedRescale(BaseAlgorithm):
    '''
    requires that the layer sets the buffer parameter &buffer=x
    '''
    input_nbands: int = 1
    output_nbands: int = 1
    output_dtype: str = "uint8"

    min: float = -1
    max: float = 1

    def __call__(self, img: ImageData) -> ImageData:
        mask = (np.isnan(img.data))[0]
        img.rescale(
            in_range=((self.min, self.max),),
            out_range=((0, 255),)
        )
        data = np.where(~mask, img.data, 0)
        modified_mask = np.where(mask, 255, 0)
        masked_array = np.ma.MaskedArray(data, mask=modified_mask)
        return ImageData(
            masked_array,
            assets=img.assets,
            crs=img.crs,
            bounds=img.bounds,
        )


algorithms: Algorithms = default_algorithms.register({
    "stravaheatmap": StravaHeatmap, 
    "bboxstats": BBoxStats,
    "stravaclahe": StravaCLAHE,
    "masked-rescale": MaskedRescale,
})
PostProcessParams: Callable = algorithms.dependency
