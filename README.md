# cwandt-pocketfiche-site
Web app to browse CW&T pocketfiche parcels

# layout

`/docs` is the static site
- `/docs/tiles` is the tile images that are loaded laziliy by Leaflet on the client
- `/docs/map.json` is the map of which tiles are claimed so the client does not waste time requesting empty tiles

# Bootstraping from old system

This new system replaces an older one that was based on PHP and a MySQL database. We need to dump the old database and files form that old system to get started. 

## 1. Download tiles

This will grab all the tiles that are listed as "claimed" in the old database and copy them down to the `tiles` directory.

```
.\download_tiles.py --server https://pocketfiche.cwandt.com --output docs/tiles
```

## 2. Create map.json

This will create a `map.json` file that can be used by the client app to know which tiles to request from the server. 

```
python create-map.py --tiles-dir docs/tiles --output docs/map.json
```
## 3. Optimize PNG files for space (optional)


Download....
```
https://github.com/oxipng/oxipng
```

...and run this comand from inside the docs/tiles directory...

```
oxipng "*.png" -o max --strip all --zopfli
```

- `-o max` always optimize for maximum compression even if slow
- `--strip all` remove all metadata
- `--zopfli` " Use the much slower but stronger Zopfli compressor for main compression trials."


It is quite effective! Here are the results from the initial set of tiles:

Before:
353,328 byte

After:
140,119 bytes

...although it seems these scrapted files might have been munged already which might make this optimization more effective? :/

I would at least run this when making the final publish at the end of the campaign, and maybe occasionally before then. 


# Running the app

It is now all static, so no deploy or run needed! As long as the client can get to `map.json` and `tiles/` on a static web server, it should work. :)

# Notes


## Tiles

Our grid is 38 columns wide and 38 rows tall, so a total of 38*38 = 1444 possible tiles (A1 through AL38). A1 is in the top left corner, and AL38 is in the bottom right corner, which is kinda counter intuitive. But at least we can make a simple mapping to this from Leaflet's (lat,lng) coordinates using a `getTileUrl` function.

In practice, there are fewer tiles because the claimable radius is much smaller than the grid size. Bu tnot that I will reservbe at least one tile outside this radium for my purposes. :)

From the old system, each tile is [column][row] (e.g. A1, B2, ... AL38), which is confusing becuase it is (y,x) instead of (x,y). 

Every tile is 500x500 pixels. 

We keep all populated tiles in the `tiles` directory. We use the `map.json` file to know which tiles to request from the server.

### Zooming

We only have the actuial tile files on the server, so we will let the browser do all the scaling in both directions.

We will always start at at zoom level that fits the centermost 2x2 tiles in the canvas (and maybe a 50% min margin around that so people can see there is more in each directtion). These are special tiles that CW&T made and we want them to be the first thing the user sees.  

Zoom=1 is one tile per parcel. We can't have more resolution than the actual parcels so we will let the borwser do the scaling. (maybe fun to do an easter egg if they zoom in too far?)







