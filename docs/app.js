/*
  Pocketfiche Parcels Viewer (minimal prototype)

  - Uses Leaflet with L.CRS.Simple so that map units == pixels
  - Loads map.json to determine which tiles to request
  - Renders tiles via a custom L.TileLayer that overrides getTileUrl
    • Maps Leaflet tile coords -> our (row, col) grid
    • Returns real image URLs for claimed tiles
    • Returns a local sky-blue data URL for non-existent/unclaimed tiles
  - Fits the view to the extent of claimed tiles (falls back to full grid)

  You can refine visuals and features later (styling, UI, interactions).
*/

(() => {
  // ---- Constants matching the server/grid ----
  // Note that all sizes are one dimensional units for now since everything is square. 

  // --- Facts from the kickstarter campaign
  const PIXELS_PER_PARCELTILE = 500             // This is how big the parcel images from users are
  const PARCEL_COLS = 38;                       // Total columns in the grid
  const PARCEL_ROWS = 38;                       // Total rows in the grid

  // Defined by the kickstarter campaign (and miles's process)
  const um_per_parcel_pixel = 1   // Our dot size for the parcel images people give us
  const disk_diameter_um = 25000  // 25mm

  // I picked this so that the most intrinsicalkly zoomed tile would be exactly one parcel
  // which also makes it be pixel perfect with no scaling needed. 
  const TILE_SIZE = PIXELS_PER_PARCELTILE;       


  // --- Some policy choices

  // I picked this becuase it is the lowest zoom level that lets us still fit a full world into a single tile at zoom 0
  // at zoom 6, 1 parcel = 1 tile. pixel for pixel match.
  const parcel_zoom = 6
  
  // I picked this becuase this is the most zoomed out level that needs a single tile to cover the whole world
  // Note that the disk is actually a little smaller than the world. The disk just needs to completely fit into a single tile. 
  const world_zoom = 0

  // How big in real size is, say, a world tile pixel compared to pixel in a parcel tile pixel?
  const parcels_per_world_ratio = Math.pow(2,parcel_zoom-world_zoom)  

  // We defined 1 mapunit to be 1 pixel wide at world zoom
  const mapunit_per_worldtile = TILE_SIZE

  // --- calculate constants to help with layout

  const mapunit_per_parceltile = mapunit_per_worldtile / parcels_per_world_ratio 

  const UM_PER_MAPUNIT =  (um_per_parcel_pixel * PIXELS_PER_PARCELTILE) / mapunit_per_parceltile 

  console.log("UM_PER_MAPUNIT", UM_PER_MAPUNIT);

  // Where to find the tiles (relative to the html file)
  const TILE_URL_TEMPLATE = "world/{z}/{x}/{y}.png";

  // ---- Utilities ----
  // Convert letters like 'A'..'Z','AA','AB' to 0-based row index
  function lettersToIndex(letters) {
    let n = 0;
    for (let i = 0; i < letters.length; i++) {
      const c = letters.charCodeAt(i) - 64; // 'A' -> 1
      if (c < 1 || c > 26) return null;
      n = n * 26 + c;
    }
    return n - 1; // 0-based
  }

  // Convert 0-based index to letters (for tooltips / debug)
  function indexToLetters(idx) {
    idx = idx + 1; // Excel-like 1-based
    let s = '';
    while (idx > 0) {
      idx -= 1;
      s = String.fromCharCode(65 + (idx % 26)) + s;
      idx = Math.floor(idx / 26);
    }
    return s;
  }

  // Parse a coordinate string like 'H4' or 'AA12'
  function parseCoord(coord) {
    const m = /^([A-Z]+)(\d+)$/.exec(coord);
    if (!m) return null;
    const letters = m[1];
    const colNum = parseInt(m[2], 10);
    if (!Number.isFinite(colNum)) return null;
    const rowIdx = lettersToIndex(letters);
    if (rowIdx == null) return null;

    // Numeric part is 1-based in keys (A1 is top-left). Convert to 0-based index.
    const colIdx = colNum - 1;
    return { row: rowIdx, col: colIdx, letters, number: colNum };
  }

  // Build image URL for a coordinate key (e.g., 'H4' -> tiles/tile-H4.png)
  function tileUrlFromCoord(coord) {
  return `${TILE_DIR}/tile-${coord}.png`;
  }

  // Compute pixel bounds for a given row/col (top-left, bottom-right)
  function tilePixelBounds(row, col) {
    const x0 = col * TILE_SIZE;
    const y0 = row * TILE_SIZE;
    const x1 = x0 + TILE_SIZE;
    const y1 = y0 + TILE_SIZE;
    // Leaflet expects [[y, x], [y, x]] when using CRS.Simple
    return [[y0, x0], [y1, x1]];
  }

  // Generate a local 500x500 SVG tile as a data URL that includes
  // request coordinates and a bounding box for easy visual debugging.
  function makeDebugTileDataURL( coords, title ) {
    const w = TILE_SIZE;
    const h = TILE_SIZE;
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
        <rect x="1.5" y="1.5" width="${w - 3}" height="${h - 3}" fill="#f0f8ff" stroke="#0aa" stroke-width="1" stroke-dasharray="5,5"/>
        <g font-family="monospace" fill="#000">
          <text x="16" y="36" font-size="24">
            z=${coords.z}
            x=${coords.x}
            y=${coords.y}
          </text>
          <text x="${w / 2}" y="${h / 2}" font-size="64" text-anchor="middle" dominant-baseline="middle">${title}</text>
          <g transform="translate(16, 16)">
            <line x1="0" y1="100" x2="500" y2="100" stroke="#000" stroke-width="1" />
            <line x1="0" y1="200" x2="500" y2="200" stroke="#000" stroke-width="2" />
            <line x1="0" y1="300" x2="500" y2="300" stroke="#000" stroke-width="4" />
            <line x1="0" y1="400" x2="500" y2="400" stroke="#000" stroke-width="8" />
          </g>

        </g>
      </svg>
    `;
    //console.log("svg", svg);
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
  }


  // Local sky-blue tile (very light) as a PNG data URL, sized to TILE_SIZE with 1px white border
  const UNCLAIMED_TILE_URL = (() => {
    console.log("Making SKY_BLUE_URL");
    const canvas = document.createElement('canvas');
    canvas.width = TILE_SIZE;
    canvas.height = TILE_SIZE;
    const ctx = canvas.getContext('2d');
    
    // Draw white background (border)
    ctx.fillStyle = 'white';
    ctx.fillRect(0, 0, TILE_SIZE, TILE_SIZE);
    
    // Draw blue interior with 1px inset
    ctx.fillStyle = '#cfefff';
    ctx.fillRect(1, 1, TILE_SIZE - 2, TILE_SIZE - 2);
    
    return canvas.toDataURL('image/png');
  })();


  // Returns a single pixel tile
  const NONEXISTANT_TILE_URL = (() => {
    const canvas = document.createElement('canvas');
    canvas.width = 1;
    canvas.height = 1;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = 'black';
    ctx.fillRect(0, 0, 1, 1);
    return canvas.toDataURL();
  })();


  // Bear with me here...
  // The CRS.Simple is hardcoded to have (0,0) in the top-left corner and there is no other CRS that has a flat world with (0,0) in the center. 
  // My brain can not handle this, so we need to create our own CRS that has (0,0) in the center and normal (x,y) coordinates.


  // Origin (0,0) at tile center. x→right, y→up.
  // One map unit = one pixel at zoom 0
  // so the whole world goes from upper left (-250,250) to bottom right (250,-250)
  const CRS_CENTERED = L.extend({}, L.CRS.Simple, {
  transformation: new L.Transformation(1, TILE_SIZE/2, -1, TILE_SIZE/2)
  });    


  // ---- Map init ----
  const map = L.map('map', {
    crs: CRS_CENTERED,
    // minZoom: -4, 
    // maxZoom: 5,
    minZoom: -6,
    maxZoom: 10,
    zoomControl: true,
    attributionControl: false
    // Stick with SVG so that our circles will look sharp at all zoom sizes
  });


  // In our world one unit of latlong is one pixel at zoom 0
  // so the whole world goes from upper left (-250,250) to bottom right (250,-250)
  const worldBounds = L.latLngBounds([[-(TILE_SIZE/2), (TILE_SIZE/2)], [(TILE_SIZE/2), -(TILE_SIZE/2)]]);

  // panning limits
  map.setMaxBounds(worldBounds.pad(0.1)); // small padding to allow gentle panning  

  // Set initial view to center of grid
  map.setView([0,0], 0);

  // Feelling debuggy - might delete
  // Passive status control: zoom + center (live)
  const StatusControl = L.Control.extend({
    options: { position: 'bottomleft', digits: 5, zoomDigits: 2 },
    onAdd(map) {
      const el = L.DomUtil.create('div', 'leaflet-bar');
      el.style.padding = '4px 8px';
      el.style.font = '12px monospace';
      el.style.pointerEvents = 'none';
      el.style.backgroundColor = '#c6f4d6';

      const update = () => {
        const z = map.getZoom();
        const c = map.getCenter();
        el.textContent = `z ${z.toFixed(this.options.zoomDigits)}  center ( y=${c.lat.toFixed(this.options.digits)} , x=${c.lng.toFixed(this.options.digits)} )`;
      };

      map.on('move zoom', update);
      update();              // initial render
      this._off = () => map.off('move zoom', update);
      return el;
    },
    onRemove() { this._off && this._off(); }
  });

  // Create the control but don't add it yet - we'll add it via layer control
  const statusControl = new StatusControl({ position: 'bottomleft' });

  // Custom scale bar that shows correct scale for our tiny world
  // Range: 10nm to 100mm
  // Scale bar never longer than 50% of window width
  // Use power of ten sizes with nm, um, or mm units

  const ScaleControl = L.Control.extend({
    options: {
      position: 'bottomright',
      maxWidth: 0.5  // Maximum width as fraction of window width (50%)
    },

    onAdd: function(map) {
      this._map = map;
      
      // Create the scale bar container
      const container = L.DomUtil.create('div', 'leaflet-control-scale');
      container.style.background = 'rgba(0, 0, 0, 0.5)';
      container.style.border = '2px solid #fff';
      container.style.padding = '0';
      container.style.boxSizing = 'border-box';
      
      // Create the inner content element for text
      this._scaleText = L.DomUtil.create('div', 'scale-text', container);
      this._scaleText.style.textAlign = 'center';
      this._scaleText.style.padding = '2px 8px';
      this._scaleText.style.whiteSpace = 'nowrap';
      this._scaleText.style.lineHeight = '1';
      
      this._container = container;
      
      // Update on zoom and moveend
      map.on('zoom move', this._update, this);
      this._update();
      
      return container;
    },

    onRemove: function(map) {
      map.off('zoom move', this._update, this);
    },

    _update: function() {
      const zoom = this._map.getZoom();
      
      // Calculate nanometers per pixel at this zoom level
      // At zoom 6, 1 pixel = 1 µm = 1000 nm
      // Each zoom level doubles/halves the scale
      const nanometersPerPixel = 1000 / Math.pow(2, zoom - parcel_zoom);
      
      // Get maximum allowed width in pixels (50% of window width)
      const maxWidthPixels = Math.floor(window.innerWidth * this.options.maxWidth);
      
      // Define available scale sizes (all in nanometers)
      // Power of 10: 10nm, 100nm, 1um, 10um, 100um, 1mm, 10mm, 100mm
      const scales = [
        { nm: 1000, label: '1um' },
        { nm: 10000, label: '10um' },
        { nm: 100000, label: '100um' },
        { nm: 1000000, label: '1mm' },
        { nm: 10000000, label: '10mm' },
        { nm: 100000000, label: '100mm' },
        { nm: 1000000000, label: '1m' }
      ];
      
      // Find the largest scale that fits within maxWidth
      // Start from largest and work down to find the biggest one that fits
      let selectedScale = scales[0]; // Default to smallest (10nm)
      
      for (let i = scales.length - 1; i >= 0; i--) {
        const scale = scales[i];
        const widthPixels = scale.nm / nanometersPerPixel;
        
        if (widthPixels <= maxWidthPixels) {
          selectedScale = scale;
          break;
        }
      }
      
      // Calculate the actual width in pixels for the selected scale
      const barWidthPixels = Math.round(selectedScale.nm / nanometersPerPixel);
      
      // Update the container width and text
      this._container.style.width = barWidthPixels + 'px';
      this._scaleText.textContent = selectedScale.label;
    }
  });
  
  // Create the scale control but don't add it yet - we'll add it via layer control
  const scaleControl = new ScaleControl({ position: 'bottomright' });

  const DebugTileLayer = L.TileLayer.extend({
    getTileUrl: function (coords) {
    
      // debug
      return makeDebugTileDataURL(  coords , "debug");
    },
  });


  // Debug tile layer shows coords in inside each tile
  // Note that the URL is not used but it has to be there. 
  const debugLayer = new DebugTileLayer(  TILE_URL_TEMPLATE , {       
      tileSize: TILE_SIZE,  
      bounds: worldBounds,
      minNativeZoom: 0,
      maxNativeZoom: 6,
      minZoom: -6, 
      maxZoom: 10,        
      noWrap: true,
      updateWhenIdle: true,

  });

  // This is the main tile layer that shows the parcels. It will intionally fail to load tiles that are not found.
  // I think a 404 is faster than returning a 1px placeholder tile?

  const parcelsLayer = new L.TileLayer(  TILE_URL_TEMPLATE , {       
    tileSize: TILE_SIZE,  
    bounds: worldBounds,
    minNativeZoom: 0,
    maxNativeZoom: 6,
    minZoom: -6, 
    maxZoom: 10,        
    noWrap: true,
    updateWhenIdle: true,
  });      


  // --- Gold disk circle
  
  // Create an overlay layer with a circle that shows the claimable radius
  // The color and width of the circle are defined in style.css
  
  // Create a custom pane for the gold disk so it renders BEHIND tiles
  // Default panes: tilePane (z-index 200), overlayPane (z-index 400)
  // We need z-index < 200 to be behind tiles
  map.createPane('goldDiskPane');
  map.getPane('goldDiskPane').style.zIndex = 150;
  
  const circleLayer = L.layerGroup();
  
  const innerDiameterMicrometers = disk_diameter_um;
  const innerRadiusMicrometers = innerDiameterMicrometers / 2;
  const radiusMapUnits = innerRadiusMicrometers / UM_PER_MAPUNIT;
  
  // Create circle centered at origin (0, 0)
  // Default to bright color (#ffad1f)
  const circle = L.circle([0, 0], {
    radius: radiusMapUnits,
    className: 'gold-disk-circle',
    fillOpacity: 1,     // Override Leaflet's default 0.2 opacity
    pane: 'goldDiskPane',  // Use custom pane to render behind tiles
    interactive: false  // Don't capture mouse events
  });
  
  circleLayer.addLayer(circle);
  
  // Create a toggle layer for switching between bright and toned-down colors
  const toneDownLayer = L.layerGroup();
  toneDownLayer.onAdd = function(map) {
    // Switch to toned-down color
    circle._path.classList.remove('gold-disk-circle');
    circle._path.classList.add('gold-disk-circle-toned');
  };
  toneDownLayer.onRemove = function(map) {
    // Switch back to bright color
    circle._path.classList.remove('gold-disk-circle-toned');
    circle._path.classList.add('gold-disk-circle');
  };

  // --- Create grid lines

  const gridLayer = L.layerGroup();
  
  // We need to use map units for the grid lines
  // We want spacing between lines to be 1 tile at zoom 6 (the definition of zoom 6 is 1 tile is one parcel)

  // a grid line between every parcel

  const GRID_SPACING_MAPUNITS = mapunit_per_parceltile;

  // Use the gold disk radius to constrain grid lines within the circle
  // For a circle centered at (0,0) with radius R:
  // - Horizontal line at y=y0 intersects at x = +/- SQRT(R^2 - y0^2)
  // - Vertical line at x=x0 intersects at y = +/- SQRT(R^2 - x0^2)
  // 
  // Additionally, clip to the shorter of:
  // 1. Circle boundary (rounded down to nearest parcel boundary)
  // 2. Edge of 38x38 parcel grid
  
  const R = radiusMapUnits; // Circle radius in map units
  
  // Grid boundary: 38x38 grid centered at origin means ±19 parcels from center
  const gridHalfWidth = (PARCEL_COLS / 2) * GRID_SPACING_MAPUNITS;
  const gridHalfHeight = (PARCEL_ROWS / 2) * GRID_SPACING_MAPUNITS;
  
  // Horizontal lines (constant y, varying x)
  for (let i = -1 * (PARCEL_COLS/2); i <= PARCEL_COLS/2; i += 1) {
    const y = i * GRID_SPACING_MAPUNITS;
    
    // Check if this line intersects the circle
    if (Math.abs(y) <= R) {
      // Calculate x intersection with circle: x = ±√(R² - y²)
      const xCircle = Math.sqrt(R * R - y * y);
      
      // Round down to nearest parcel boundary
      const xCircleParcels = Math.floor(xCircle / GRID_SPACING_MAPUNITS);
      const xCircleRounded = xCircleParcels * GRID_SPACING_MAPUNITS;
      
      // Take the minimum of circle extent and grid extent
      const xExtent = Math.min(xCircleRounded, gridHalfWidth);
      
      // Only draw if extent is positive
      if (xExtent > 0) {
        const line = L.polyline([
          [y, -xExtent],  // Start point (y, -x)
          [y, xExtent]    // End point (y, +x)
        ], { className: 'grid-line' });
        gridLayer.addLayer(line);
      }
    }
  }

  // Vertical lines (constant x, varying y)
  for (let i = -1 * (PARCEL_ROWS/2); i <= PARCEL_ROWS/2; i += 1) {
    const x = i * GRID_SPACING_MAPUNITS;
    
    // Check if this line intersects the circle
    if (Math.abs(x) <= R) {
      // Calculate y intersection with circle: y = abs(sqrt(R^2 - x^2)
      const yCircle = Math.sqrt(R * R - x * x);
      
      // Round down to nearest parcel boundary
      const yCircleParcels = Math.floor(yCircle / GRID_SPACING_MAPUNITS);
      const yCircleRounded = yCircleParcels * GRID_SPACING_MAPUNITS;
      
      // Take the minimum of circle extent and grid extent
      const yExtent = Math.min(yCircleRounded, gridHalfHeight);
      
      // Only draw if extent is positive
      if (yExtent > 0) {
        const line = L.polyline([
          [-yExtent, x],  // Start point (-y, x)
          [yExtent, x]    // End point (+y, x)
        ], { className: 'grid-line' });
        gridLayer.addLayer(line);
      }
    }
  }

  // --- Layer Control
  // Add layers control for toggling overlay layers
  
  const baseLayers = {
    "Parcels": parcelsLayer
  };
  
  // Create a wrapper layer for the status control so it can be toggled
  const statusControlLayer = L.layerGroup();
  statusControlLayer.onAdd = function(map) {
    map.addControl(statusControl);
  };
  statusControlLayer.onRemove = function(map) {
    map.removeControl(statusControl);
  };
  
  // Create a wrapper layer for the scale control so it can be toggled
  const scaleControlLayer = L.layerGroup();
  scaleControlLayer.onAdd = function(map) {
    map.addControl(scaleControl);
  };
  scaleControlLayer.onRemove = function(map) {
    map.removeControl(scaleControl);
  };
  
  const overlayLayers = {
    "Gold Disk": circleLayer,
    "Tone it down": toneDownLayer,
    "Grid Lines": gridLayer,
    "Status Display": statusControlLayer,
    "Scale Bar": scaleControlLayer,
    "Debug Tiles": debugLayer,
  };
  
  // Add the layers control to the map
  L.control.layers(baseLayers, overlayLayers, { position: 'topright' , hideSingleBase: true }).addTo(map);
  
  // Add default layers - gold disk first (behind), then parcels (on top)
  circleLayer.addTo(map);
  parcelsLayer.addTo(map);
  scaleControlLayer.addTo(map);

  


  // const parcels = new DebugTileLayer(  'world/tiles/{z}/{x}/{y}.png' ,{
  //   tileSize: TILE_SIZE,

  //   // So I am only going to provide tiles at the native resolution (zoom 0) and let Leaflet do any other scaling up or down
  //   // locally. minNativeZoom must match or be lower than the map's minZoom to enable auto-scaling.
  //   minNativeZoom: 0,
  //   maxNativeZoom: 6,
  //   minZoom: -4, 
  //   maxZoom: 10,        
  //   noWrap: true,
  //   updateWhenIdle: true,
  // }).addTo(map);

  // // Lets test with a static tile
  // const parcels = new L.TileLayer( '500x500-test.png', {

  //   tileSize: TILE_SIZE,

  //   // So I am only going to provide tiles at the native resolution (zoom 0) and let Leaflet do any other scaling up or down
  //   // locally. minNativeZoom must match or be lower than the map's minZoom to enable auto-scaling.
  //   minNativeZoom: 0,
  //   maxNativeZoom: 0,
  //   minZoom: -2, 
  //   maxZoom: 2,
  //   noWrap: true,
  //   updateWhenIdle: true,
  // }).addTo(map);

  // For now, show the whole world at startup
  // todo: zoom into 2x2 center parcels
  //map.fitBounds(worldBounds, { padding: [80, 80] });

  // Click handler: fly to center of clicked parcel at parcel zoom level
  map.on('click', (e) => {
    const x = e.latlng.lng;  // x coordinate in map units
    const y = e.latlng.lat;  // y coordinate in map units
    
    // Calculate which parcel was clicked (centered grid coordinates)
    const parcelX = Math.floor(x / mapunit_per_parceltile);
    const parcelY = Math.floor(y / mapunit_per_parceltile);
    
    // Convert to 0-based row/col indices for display
    const col = parcelX + PARCEL_COLS / 2;
    const row = parcelY + PARCEL_ROWS / 2;
    
    if (row >= 0 && row < PARCEL_ROWS && col >= 0 && col < PARCEL_COLS) {
      const coord = `${indexToLetters(row)}${col + 1}`;
      console.log('Clicked tile:', coord, { row, col });
      
      // Calculate center of the parcel in map units
      const centerX = (parcelX + 0.5) * mapunit_per_parceltile;
      const centerY = (parcelY + 0.5) * mapunit_per_parceltile;
      
      // Fly to the center of the parcel at zoom level 6
      map.flyTo([centerY, centerX], parcel_zoom);
    }
  });
})();
