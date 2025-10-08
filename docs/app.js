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

  const TILE_SIZE = 500;       // Each tile is 500x500 pixels
  const COLS = 38;             // Total columns in the grid
  const ROWS = 38;             // Total rows in the grid


  // Calculate um per mapunit. We will use this for drawing physiocal sized objects on the map using map units.
  const UM_PER_MAPUNIT = (() => {

    // We picked our zooms to make 1 tile pixel = 1 parcel pixel at zoom=6
    const um_per_tilepixelz6 = 1   

    // We also defined 1 mapunit to be 1 tile wide at zoom=0
    const mapunit_per_tilepixel_z0 = 1

    // Just math, every zoom level is double the size of the previous
    const tilepixelz6_per_tilepixelz0 = Math.pow(2,6-0)

    const tilepixelz6_per_mapunit = tilepixelz6_per_tilepixelz0 * mapunit_per_tilepixel_z0

    // This is the answer we need 
    return um_per_tilepixelz6 * tilepixelz6_per_mapunit

  })()


  // This parameter is straight from the kickstarter campaign
  const CLAIMABLE_RADIUS_UM = 25000

  console.log("UM_PER_MAPUNIT", UM_PER_MAPUNIT);

  // Paths relative to docs/
  const MAP_JSON_URL = 'map.json';
  const TILE_DIR = 'tiles';

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

  // add it
  map.addControl(new StatusControl({ position: 'bottomleft' }));

  // Custom scale bar that shows correct scale for our tiny world
  // At zoom 6: 1 pixel = 1 µm, doubling every zoom level. 
  // TODO: THIS IS WRONG. FIGURE OUT WHY.
  const MicrometerScale = L.Control.Scale.extend({
    _updateMetric: function (maxMeters) {
      // Get current zoom level - each zoom level doubles the scale
      const zoom = this._map.getZoom();
      // At zoom 5, 1 pixel = 2 µm
      // At zoom 6, 1 pixel = 1 µm. 
      // At zoom 7, 1 pixel = 0.5 µm
      const micrometersPerPixel = 2 / Math.pow(2, 6-zoom);

      console.log("micrometersPerPixel", micrometersPerPixel);

      const pixelsPerMicron = 1 / micrometersPerPixel;
      console.log("pixelsPerMicron", pixelsPerMicron);

      
      // Choose appropriate scale bar size and unit
      const scales = [
        { value: 1, label: '1 µm' },
        { value: 2, label: '2 µm' },
        { value: 5, label: '5 µm' },
        { value: 10, label: '10 µm' },
        { value: 20, label: '20 µm' },
        { value: 50, label: '50 µm' },
        { value: 100, label: '100 µm' },
        { value: 200, label: '200 µm' },
        { value: 500, label: '500 µm' },
        { value: 1000, label: '1 mm' },
        { value: 2000, label: '2 mm' },
        { value: 5000, label: '5 mm' },
        { value: 10000, label: '1 cm' },
        { value: 20000, label: '2 cm' },
        { value: 50000, label: '5 cm' },
        { value: 100000, label: '10 cm' },
        { value: 200000, label: '20 cm' },
        { value: 500000, label: '50 cm' },
        { value: 1000000, label: '1 m' }
      ];
                  

      // Update the scale bar
      this._updateScale(this._mScale, "1um", pixelsPerMicron);
    }
  });
  
  map.addControl(new MicrometerScale({ position: 'bottomright', imperial: false }));

  const DebugTileLayer = L.TileLayer.extend({
    getTileUrl: function (coords) {
    
      // debug
      return makeDebugTileDataURL(  coords , "debug");
    },
  });


  // Debug tile layer shows coords in inside each tile
  const parcels = new DebugTileLayer(  'world/tiles/{z}/{x}/{y}.png' , {       
      tileSize: TILE_SIZE,  
      bounds: worldBounds,
      minNativeZoom: 0,
      maxNativeZoom: 6,
      minZoom: -6, 
      maxZoom: 10,        
      noWrap: true,
      updateWhenIdle: true,

  }).addTo(map);

  // This is the main tile layer that shows the parcels. It will intionally fail to load tiles that are not found.
  // I think a 404 is faster than returning a 1px placeholder tile?

  const parcelsLayer = new L.TileLayer(  'world/{z}/{x}/{y}.png' , {       
    tileSize: TILE_SIZE,  
    bounds: worldBounds,
    minNativeZoom: 0,
    maxNativeZoom: 6,
    minZoom: -6, 
    maxZoom: 10,        
    noWrap: true,
    updateWhenIdle: true,
  }).addTo(map);      

  // Create an overlay layer with a circle that shows the claimable radius
  // The color and width of the circle are defined in style.css
  
  const circleLayer = L.layerGroup().addTo(map);
  
  const innerDiameterMicrometers = CLAIMABLE_RADIUS_UM;
  const innerRadiusMicrometers = innerDiameterMicrometers / 2;
  const radiusMapUnits = innerRadiusMicrometers / UM_PER_MAPUNIT;
  
  // Create circle centered at origin (0, 0)
  const circle = L.circle([0, 0], {
    radius: radiusMapUnits,
    className: 'claimable-circle',
    interactive: false  // Don't capture mouse events
  });
  
  circleLayer.addLayer(circle);


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

  // Optional: click to log the tile coordinate under the cursor
  map.on('click', (e) => {
    const col = Math.floor(e.latlng.lng / TILE_SIZE);
    const row = Math.floor(e.latlng.lat / TILE_SIZE);
    if (row >= 0 && row < ROWS && col >= 0 && col < COLS) {
      const coord = `${indexToLetters(row)}${col + 1}`;
      console.log('Clicked tile:', coord, { row, col });
    }
  });
})();
