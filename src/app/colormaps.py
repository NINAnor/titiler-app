"""dependencies.

app/dependencies.py

"""

import json

from typing import Dict, Optional, Literal
from typing_extensions import Annotated

import numpy
import matplotlib
from rio_tiler.colormap import parse_color
from rio_tiler.colormap import cmap as default_cmap
from fastapi import HTTPException, Query

def generate_colorblind_palette():
    cm = matplotlib.colors.LinearSegmentedColormap.from_list("internal", ['#f0f921', '#fdca26', '#fb9f3a', '#ed7953', '#d8576b', '#bd3786', '#9c179e', '#7201a8', '#46039f', '#0d0887'], 256)
    x = numpy.linspace(0, 1, 256)
    cmap_vals = cm(x)[:, :]
    cmap_uint8 = (cmap_vals * 255).astype('uint8')
    cmap_uint8[0][3] = 0
    
    return {idx: value.tolist() for idx, value in enumerate(cmap_uint8)}


def generate_binary_colormap():
    return {
        0: (0, 0, 0, 0),
        1: (240, 249, 33, 255)
    }

default_cmap = default_cmap.register({"colorblind": generate_colorblind_palette(), "nbinary": generate_binary_colormap()})


def ColorMapParams(
    colormap_name: Annotated[  # type: ignore
        Literal[tuple(default_cmap.list())],
        Query(description="Colormap name"),
    ] = None,
    colormap: Annotated[
        str,
        Query(description="JSON encoded custom Colormap"),
    ] = None,
    colormap_type: Annotated[
        Literal["explicit", "linear"],
        Query(description="User input colormap type."),
    ] = "explicit",
) -> Optional[Dict]:
    """Colormap Dependency."""
    if colormap_name:
        return default_cmap.get(colormap_name)

    if colormap:
        try:
            cm = json.loads(
                colormap,
                object_hook=lambda x: {int(k): parse_color(v) for k, v in x.items()},
            )
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400, detail="Could not parse the colormap value."
            )

        return cm
    else:
        return None

