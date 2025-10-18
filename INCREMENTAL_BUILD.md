# Incremental Build System

## Overview

`incremental_build.py` uses **file timestamps** to efficiently rebuild only out-of-date tiles, similar to traditional build systems like `make` or `ninja`.

## How It Works

We will end up with a full world in the output directory, but only the tiles that need to be rebuilt will be rebuilt.

Each zoom level n of the world will have tiles in an 2^n x 2^n grid, so (2^n)^2 tiles in total in each zoom level. All tiles are built. This is nessisary since if Leaflet tries to load a tiles and gets a 404, then it will cache that the file is missing and not update if we later add the tile.


### Timestamp-Based Dependencies

We only build tiles if they are out of date. To check if a tile is out of date, we generate a list of files that a tile is dependent on. If any of the files are newer than the tile, the tile is rebuilt.

#### dependencies

Zoom 6 tiles depend on the corresponding parcel files. We have a function that tries to map a tile x,y to a parcel filename. If the x,y does not map to a parcel, or it does map to a parcel but there is not file for that parcel, we create a transparent single pixel PNG tile with the current time/date. Otherwise if the parcel file exists and is newer than the tile, the tile is rebuilt by simply coping the parcel tile to the tile file.

For all zoom levels 0<=n<6, a tile depends on the 4 tiles at zoom n+1 that make up the zoom level tile. If any of the those 4 tiles on zooom n+1 have a newer timestamp than the tile, the tile is rebuilt by combining the 4 zoom 6 tiles.


## Usage

### Basic Usage

```bash
# Run incremental build
python incremental_build.py

# Specify custom directories
python incremental_build.py --parcels-dir parcels --output-dir docs/world

# Force full rebuild (clears all tiles)
python incremental_build.py --force
```

## How Timestamps Work

### File Modification Time
The system uses `st_mtime` (modification time) from the file system:
- Updated when a file is created or modified
- Preserved when files are copied (usually)
- Compared using simple `>` operator

### Force Rebuild
The `--force` flag:
- Deletes entire output directory
- Runs full build via `build_world.py`

