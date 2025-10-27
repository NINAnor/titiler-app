from attrs import define
from typing import Annotated
from titiler.core.factory import BaseFactory
import morecantile
from fastapi import Response, Path, Query, Request
from typing import Dict, Any
import jinja2
from starlette.templating import Jinja2Templates

import duckdb

jinja2_env = jinja2.Environment(
    autoescape=jinja2.select_autoescape(["html", "xml"]),
    loader=jinja2.ChoiceLoader([jinja2.PackageLoader(__package__, "templates")]),
)
DEFAULT_TEMPLATES = Jinja2Templates(env=jinja2_env)

con = duckdb.connect()
con.execute("load spatial")

endpoint_params: Dict[str, Any] = {
    "responses": {
        200: {
            "content": {
                "application/x-protobuf": {},
            },
            "description": "Return an MVT.",
        }
    },
    "response_class": Response,
}


@define(kw_only=True)
class VectorFactory(BaseFactory):
    supported_tms: morecantile.defaults.TileMatrixSets = morecantile.tms
    templates: Jinja2Templates = DEFAULT_TEMPLATES

    def register_routes(self):
        self.tiles()
        self.preview()

    def tiles(self):
        @self.router.get(
            "/tiles/{z}/{x}/{y}.pbf",
            operation_id="getTile",
        )
        def tile(
            z: Annotated[
                int,
                Path(
                    description="Identifier (Z) selecting one of the scales defined in the TileMatrixSet and representing the scaleDenominator the tile.",
                ),
            ],
            x: Annotated[
                int,
                Path(
                    description="Column (X) index of the tile on the selected TileMatrix. It cannot exceed the MatrixHeight-1 for the selected TileMatrix.",
                ),
            ],
            y: Annotated[
                int,
                Path(
                    description="Row (Y) index of the tile on the selected TileMatrix. It cannot exceed the MatrixWidth-1 for the selected TileMatrix.",
                ),
            ],
            url: Annotated[str, Query(description="path to the resource")],
            source_crs: Annotated[
                int, Query(description="EPSG code of the source CRS")
            ] = 4326,
            geometry_field: Annotated[
                str, Query(description="Name of the geometry field")
            ] = "geom",
            invert_axys: Annotated[
                bool,
                Query(
                    description="Invert latitude and longitude while converting to WebMercator"
                ),
            ] = True,
        ):
            with con.cursor() as local_con:
                tile_blob = local_con.execute(
                    f"""
                    SELECT ST_AsMVT({{
                        "geom": ST_AsMVTGeom( 
                            ST_Transform("{geometry_field}", $4, 'EPSG:3857', always_xy := $5),
                            ST_Extent(ST_TileEnvelope($1, $2, $3))
                            )
                        }})
                    FROM '{url}'
                    WHERE ST_Intersects("{geometry_field}", ST_Transform(ST_TileEnvelope($1, $2, $3), 'EPSG:3857', $4, always_xy := $5))
                    USING SAMPLE reservoir(1000000 ROWS)
                    REPEATABLE (100)
                    """,
                    [z, x, y, f"EPSG:{source_crs}", invert_axys],
                ).fetchone()

            # Send the tile data as a response
            tile = tile_blob[0] if tile_blob and tile_blob[0] else b""
            return Response(tile)

    def preview(self):
        @self.router.get("/map.html", operation_id="vector_preview")
        def map(
            request: Request,
            url: Annotated[str, Query(description="path to the resource")],
            source_crs: Annotated[
                int, Query(description="EPSG code of the source CRS")
            ] = 4326,
        ):
            return self.templates.TemplateResponse(
                request,
                name="vector_preview.html",
                context={
                    "url": url,
                },
                media_type="text/html",
            )
