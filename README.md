# cwandt-pocketfiche-site
Web app to browse CW&T pocketfiche parcels

# User tldr;

This tool displays the [CW&T pocketfiche parcels](https://www.kickstarter.com/projects/cwandt/pocket-fiche/description) as they will look on the actual tiny fiche. 

You can zoom in and out use the zoom control in the upper-left corner, or a scroll wheel, or pinch to zoom on a touch device. 

You can pan by clicking and dragging on the map.

You can select which layers you want to see using the layer control in the upper-right coner.

To highlight a specific parcel, you can add a `?parcel=parcel_id` query parameter to the URL. 

The URL is updated to always reflect the current state of the map, so you can share or save that URL to capture the current view. It is meant to be like a google maps URL, except the `@` is a param ratehr than part of the path. This is so the site can be served statically. 

The coordinates start with "@" and are in lat,long map units, and @0,0 is at the center of the disk. The coordinates are followed by the radius of a view circle that will be fit into the display window. 

If only a parcel is specified, the map will center on that parcel and zoom in to show the parcel in detail. If both a parcel and a view are specified, the parcel will be highlighted, but the view will be used to center the map and set the zoom level.

# notes on those 404s

For now, if the clinet requests a tile that is not on the server I let it just return a 404 error. This happens due to not claimed parcels. 

I know this is ugly, but the 404 is simper than retruning eg a 1px transparent tile. I used to have the client download a list of available tiles on startup, but that just adds delay to the startup process and adds complexity. 

As parcels get claimed, there will be fewer 404s and they will go away completely when the kickstarter campaign is sells out (which will be very soon :) ). 


# layout

`/docs` is the static site
- `/docs/world` has all of the tiles in various zoom levels, following the openmaps convention.

# Bootstraping from old system

This new system replaces an older one that was based on PHP and a MySQL database. We need to dump the old database and files form that old system to get started. 

## 1. Download tiles

This will grab all the tiles that are listed as "claimed" in the old database and copy them down to the `tiles` directory.

```
.\download_tiles.py --server https://pocketfiche.cwandt.com --output parcels/
```

## 2. Create map.json

[Temporarily out of service]

This will create a `map.json` file that can be used by the client app to know which tiles to request from the server. 

```
python create-map.py --tiles-dir docs/tiles --output docs/map.json
```

## 2.5 Build world

This will create a `world` directory that contains all the tiles in a single file.

```
python build_world.py --parcels-dir parcels --output-dir docs/world/
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

IMPORTANT: Leaflet's CRS.Simple is a bit counterintuitive. The origin is at the bottom left corner of the map, and y increases as you go up. This is the opposite of what you might expect. 

The middle of the "world" in the the intersecttion of the center 2x2 of parcels is....

S20 T20
S19 T19

We set the center of the world to be latlong(0,0). 

### Length calculations

At zoom=6, one tile pixel = 1 parcel pixel , and 1 parcel pixel = 1um. 

At zoom=7, one tile pixel = 0.5 parcel pixel , and 1 parcel pixel = 1um, so 1 tile pixel = 0.5um. 

At zoom=0 one tile pixel = 1 * 2^6 parcel pixels, and 1 parcel pixel = 1um, so 1 tile pixel = 64um. 

At zoom=0, the world is 500 pixels wide, so 1 map unit = 64um. 

500 * 64um = 32000um = 32mm, checks out!

But our fische is only 25mm wide, so the size of the encompassing circle in mapo untis is 25mm / 64um = 0.39


size_in_um 

Which maps to coords...

(-20,18) (-20,19)
(-19,18) (-19,19)

REMEBER THAT Y STARTS 0 AT THE BOTTOM AND GETS MORE NEGATIVE AS WE GO UP! This is super confusing to me becuase Leafly is supposed to be a mapping system, and positive laditude goes up on globes. :/

Remeber that this is (y,x) not (x,y)! And also note that negative y is down. 

38*500 = 1900 so the world is 19000x19000 pixels. 19000/2 = 9500. So the center of the world is at latlng (9500,9500). This is where we will land at startup.


### Zooming

We want zoom level 0 to include the full grid of 38x38 parcles in a single 500x500 pixel tile. We also want there to be a zoom level that matches 1:1 with the actual parcel size so we get pixel-perfect view with no scaling artifacts. Zoom levels are powers of 2, so we need to find what size to make the grid at zoom 0 there is a zoom level that ends up being 1:1 with the actual parcel size. 

To figure this out, let start use the formula....

x=the zoom level with 1:1 pixels, so tile size is 500x500 in parcel pixels

so if we zoom out 1 level to a+1, the tile size will be 1000x1000 in parcel pixels. 

p(y,x)=the number of parcel pixels per tile at zoom level y, given zoom level x is level where tile size is 500x500 in parcel pixels

p(y,x) = 500 * (2 ^ (x-y))

The full world is 38 parcels * 500 pixels per parcel = 19000 parcel pixels. 

we want to full world of 19000 parcel pixels to fit in one 500 pixel tile. 

so we want to solve for x in `p(0,x) >=  19000` so that at zoom 0 the whole world fits into one tile. 

`500 * ( 2 ^ (x-0)) >= 19000`

`2 ^ (x-0) >= 19000/500`

`x-0 >= log2(38)`

`x >= log2(38)`

`x >= 5.8`

`x = 6`

Let's check our work. 

| Zoom | Parcel pixels per tile | World Dimensions in tiles |
| - | - |
| 6 | 500 | 64x64|
| 5 | 1000 | 32x32 |
| 4 | 2000 | 16x16 |
| 3 | 4000 | 8x8 |
| 2 | 8000 |  4x4 |
| 1 | 16000 | 2x2 |
| 0 | 32000 | 1x1 |

The 0th zoom level will be a little sparse, but that is OK as long as the world fits completely in one tile. 

We will allow fractional zooms becuase really in the browser you can't see individual pixels so great so it doesnt matter much. But I do want there to be a zoom level that is pixel perfect ject becuase I want it to look great for people with good monitors and good eyes. Maybe we shoudl enable the retina display mode too. 

We will always start at at zoom level that fits the centermost 2x2 tiles in the canvas (and maybe a 25-50% min margin around that so people can see there is more in each directtion). These are special tiles that CW&T made and we want them to be the first thing the user sees.  






