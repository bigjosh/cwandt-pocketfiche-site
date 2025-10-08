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

To run on the local machine (for testing)...

```
cd docs
python -m http.server 8181

...and then open http://localhost:8181 in your browser.

# Notes

## Map.json

This map is always loaded first, and it is used to know which tiles to request from the server. No point wasting time and bandwith requesting empty tiles.


## Tiles

We keep all populated tiles in the `tiles` directory. We use the `map.json` file to know which tiles to request from the server. Every tile in `/tiles`is 500x500 pixels.

Our grid is 38 columns wide and 38 rows tall, so a total of 38*38 = 1444 possible tiles (A1 through AL38). A1 is in the top left corner, and AL38 is in the bottom right corner, which is kinda counter intuitive. But at least we can make a simple mapping to this from Leaflet's (lat,lng) coordinates using a `getTileUrl` function. We also use this custom `getTileUrl` to return a locally generated placeholder image for unclaimed tiles to avoid unnecessary network requests.

In practice, there are fewer tiles because the claimable radius is smaller than the grid size. But note that I will reserve at least one tile outside this radius for my own exclusive purposes. :)

We will later add an overlay layer with a big circle to show the claimable radius. And maybe also black out the surrounding area.

## Coodinates

We are using the simple coordinate CRS (L.CRS.Simple) so that one map unit corresponds to one pixel at zoom level 0. 

The middle of the "world" in the the intersecttion of the center 2x2 of parcels is....

S20 T20
S19 T19


Which maps to coords...

(-20,18) (-20,19)
(-19,18) (-19,19)

REMEBER THAT Y STARTS 0 AT THE BOTTOM AND GETS MORE NEGATIVE AS WE GO UP! This is super confusing to me becuase Leafly is supposed to be a mapping system, and positive laditude goes up on globes. :/

Remeber that this is (y,x) not (x,y)! And also note that negative y is down. 

38*500 = 1900 so the world is 19000x19000 pixels. 19000/2 = 9500. So the center of the world is at latlng (9500,9500). This is where we will land at startup.


### Zooming

We only have the actuial tile files on the server, so we will let the browser do all the scaling in both directions.

THIS WAS VERY HARD TO FIGURE OUT SO BE CAREFUL CHANGING IT!

We will always start at at zoom level that fits the centermost 2x2 tiles in the canvas (and maybe a 25-50% min margin around that so people can see there is more in each directtion). These are special tiles that CW&T made and we want them to be the first thing the user sees.  

Zoom=0 is one tile per parcel. We can't have more resolution than the actual parcels so we will let the borwser do the scaling. (maybe fun to do an easter egg if they zoom in too far?) So hard, trust me. 





