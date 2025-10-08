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
  const WIDTH = COLS * TILE_SIZE;
  const HEIGHT = ROWS * TILE_SIZE;

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


  // ---- Map init ----
  const map = L.map('map', {
    crs: L.CRS.Simple,
    minZoom: -4, 
    maxZoom: 5,
    zoomControl: true,
    attributionControl: false
    // Stick with SVG so that our circles will look sharp at all zoom sizes
  });


  // Full grid bounds (used as a fallback and for panning limits)
  const worldBounds = L.latLngBounds([[0, 0], [HEIGHT, WIDTH]]);
  map.setMaxBounds(worldBounds.pad(0.1)); // small padding to allow gentle panning  

  // Set initial view to center of grid
  map.setView([HEIGHT / 2, WIDTH / 2], 0);

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

  // Custom scale bar that shows micrometers (µm) at zoom 0
  // At zoom 0: 1 pixel = 1 µm, doubling every zoom level
  // TODO: THIS IS WRONG. FIGURE OUT WHY.
  const MicrometerScale = L.Control.Scale.extend({
    _updateMetric: function (maxMeters) {
      // Get current zoom level - each zoom level doubles the scale
      const zoom = this._map.getZoom();
      // At zoom 0, 1 pixel = 1 µm. At zoom 1, 1 pixel = 0.5 µm, etc.
      const micrometersPerPixel = 1 / Math.pow(2, zoom);
      
      // maxMeters from Leaflet represents the pixel width we have to work with
      // Convert to micrometers
      const maxMicrometers = maxMeters * micrometersPerPixel;
      
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
      
      // Find the largest scale that fits
      let scale = scales[0];
      for (let i = 0; i < scales.length; i++) {
        if (scales[i].value <= maxMicrometers) {
          scale = scales[i];
        } else {
          break;
        }
      }
      
      // Calculate the width in pixels for this scale
      const widthInPixels = scale.value / micrometersPerPixel;
      
      // Update the scale bar
      this._updateScale(this._mScale, scale.label, widthInPixels / maxMeters);
    }
  });
  
  map.addControl(new MicrometerScale({ position: 'bottomright', imperial: false }));

  // ---- Load map.json and render ----
  fetch(MAP_JSON_URL, { cache: 'no-cache' })
    .then((r) => {
      if (!r.ok) throw new Error(`Failed to load ${MAP_JSON_URL}: ${r.status}`);
      console.log("map.json loaded");
      return r.json();
    })
    .then((mapData) => {
      // mapData is expected to be an object: { "H4": { claimed: true|false }, ... }
      console.log("mapData", mapData);
      // Dictionary mapping parcel keys to claimed status (true/false)
      const claimedDict = Object.fromEntries(
        Object.entries(mapData)
          .map(([k, v]) => [k, v && v.claimed === true])
      );


      // Custom tile layer that maps Leaflet tile coords -> our grid keys
      // and also uses a custom getTileUrl function to return a locally generated placeholder image for unclaimed tiles to avoid unnecessary network requests.
      const ParcelsTileLayer = L.TileLayer.extend({
        getTileUrl: function (coords) {
          console.log("coords", coords);

          //return makeDebugTileDataURL(  coords , "out of range");

          // debug
          // return makeDebugTileDataURL(  coords , "debug");

          // Out-of-range -> sky-blue placeholder
          // if (row < 0 || row >= ROWS || col < 0 || col >= COLS) {
          //   return makeDebugTileDataURL(  coords , "out of range");
          // }

          console.log("making tileUrl");


          // Convert the coords (y,x) into a parcel row and col
          // remember that each tile is 500x500 pixels


          // col 0 is at x=0
          const col = coords.x;

          // y starts at 0 on the bottom and goes negative as we go up. 
          const row = -coords.y 

          // now convert the row to letters...
          const rowLetters = indexToLetters(row);           

          // Keys for map.json are 1-based (A1 top-left), but filenames use 0-based numeric.
          const parcelName = `${rowLetters}${col}`; // 1-based for presence check

          console.log("row", row, "col", col, "parcelName", parcelName);

          if (parcelName in claimedDict) {

            if (claimedDict[parcelName]) {
              const tileUrl = `${TILE_DIR}/tile-${parcelName}.png`; // 0-based for actual file path
              return tileUrl;
            }

            return UNCLAIMED_TILE_URL;
          }

          // If we didn't find a tile, return the sky blue placeholder
          return NONEXISTANT_TILE_URL;
        },
      });


      // OMG, the whole problem was that you MUST supply a URL tremplate here EVEN THOUGH YOU ARE NOT ACTUALLY USING IT!
      // SO bad. so many hours wasted on this. 

      const parcels = new ParcelsTileLayer(  '500x500-test.png' ,{
        tileSize: TILE_SIZE,

        // So I am only going to provide tiles at the native resolution (zoom 0) and let Leaflet do any other scaling up or down
        // locally. minNativeZoom must match or be lower than the map's minZoom to enable auto-scaling.
        minNativeZoom: 0,
        maxNativeZoom: 0,
        minZoom: -4, 
        maxZoom: 5,        
        noWrap: true,
        updateWhenIdle: true,
      }).addTo(map);


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
    })
    .catch((err) => {
      console.error(err);
      // If map.json is missing, still show the full grid area for reference
      //map.fitBounds(worldBounds, { padding: [80, 80] });
    });
})();
