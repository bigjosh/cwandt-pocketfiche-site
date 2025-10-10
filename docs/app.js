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
  // Coordinate system: A1 is in the lower-left corner
  // - Letters (A, B, ..., Z, AA, AB, ...) represent COLUMNS, incrementing left-to-right
  // - Numbers (1, 2, 3, ...) represent ROWS, incrementing bottom-to-top
  // Tolerates an optional embedded ":" to match the format used in the kickstarter campaign (ok to have: https://stackoverflow.com/questions/2053132/is-a-colon-safe-for-friendly-url-use)
  function parseCoord(coord) {
    // Make case-insensitive by converting to uppercase
    const normalizedCoord = coord.toUpperCase().trim().replace(':', '');
    const m = /^([A-Z]+)(\d+)$/.exec(normalizedCoord);
    if (!m) return null;
    const letters = m[1];
    const rowNum = parseInt(m[2], 10);
    if (!Number.isFinite(rowNum)) return null;
    const colIdx = lettersToIndex(letters);
    if (colIdx == null) return null;

    // Letters map to column index (horizontal position)
    // Numbers map to row index (vertical position, 1-based). Convert to 0-based.
    const rowIdx = rowNum - 1;
    return { row: rowIdx, col: colIdx, letters, number: rowNum };
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
  // Explicitly create SVG renderer to ensure vector rendering
  const svgRenderer = L.svg();
  
  const map = L.map('map', {
    crs: CRS_CENTERED,
    minZoom: -7,
    maxZoom: 10,
    zoomControl: true,
    attributionControl: false,
    renderer: svgRenderer,  // Force SVG rendering for all paths
    preferCanvas: false     // Explicitly disable Canvas
  });


  // In our world one unit of latlong is one pixel at zoom 0
  // so the whole world goes from upper left (-250,250) to bottom right (250,-250)
  const worldBounds = L.latLngBounds([[-(TILE_SIZE/2), (TILE_SIZE/2)], [(TILE_SIZE/2), -(TILE_SIZE/2)]]);

  // panning limits
  map.setMaxBounds(worldBounds.pad(0.25)); // small padding to allow gentle panning  

  // Default initial view: show center 4 parcels with 25% margin
  // Center 4 parcels span from -1 to +1 parcels in both directions (2x2 grid centered at origin)
  // 25% margin means adding 0.25 * 2 = 0.5 parcels on each side
  const centerParcelSize = 2 * mapunit_per_parceltile;  // 2x2 parcels
  const margin = 0.25 * centerParcelSize;  // 25% margin on each side
  const halfExtent = (centerParcelSize / 2) + (margin / 2);  // Total half-width including margin
  const initialBounds = L.latLngBounds(
    [[-halfExtent, -halfExtent],  // Southwest corner (bottom-left)
     [halfExtent, halfExtent]]     // Northeast corner (top-right)
  );
  
  // Set default view (may be overridden by URL parameters later)
  map.fitBounds(initialBounds);

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

      this._update = update;

      map.on('move zoom', this._update);
      update();              // initial render
      return el;
    },
    onRemove() { map.off('move zoom' , this._update); }
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
      
      // Hide control at the start of zoom, update and show after zoom/move completes
      // If we don't do this then sometimes the scale bar ghets too small while zooming and looks crappy.
      // TODO: Can we make it update correctly durring the zoom?
      map.on('zoomstart', this._hide, this);
      map.on('zoomend', this._update, this);
      this._update();
      
      return container;
    },

    onRemove: function(map) {
      map.off('zoomstart', this._hide, this);
      map.off('zoomend', this._update, this);
    },

    _hide: function() {
      this._container.style.visibility = 'hidden';
    },

    _update: function() {
      const zoom = this._map.getZoom();
      
      // Get maximum allowed width in pixels (50% of window width)
      const maxWidthPixels = Math.floor(window.innerWidth * this.options.maxWidth);

      // Variables to hold the final bar width and label
      let barWidthPixels;
      let label;

      // At far zoom levels (-7 to -4), show astronomical scale (AU)
      if (zoom <= -4) {
        // Calculate pixels per map unit at current zoom
        // At zoom 0, 1 map unit = 1 pixel
        // At zoom -1, 1 map unit = 0.5 pixels (zoomed out 2x)
        // At zoom -4, 1 map unit = 0.0625 pixels (zoomed out 16x)
        const pixelsPerMapUnit = Math.pow(2, zoom);
        
        // Define available AU scales
        const auScales = [
          { factor: 0.01, label: '0.01 AU' },
          { factor: 0.1, label: '0.1 AU' },
          { factor: 1.0, label: '1 AU' },
          { factor: 10.0, label: '10 AU' }
        ];
        
        // Create a temporary canvas to measure text width
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        ctx.font = '12px monospace'; // Match the scale bar font
        
        const PADDING = 16; // Space padding on each end (8px per side)
        
        // Find the smallest AU scale where the label fits inside the bar
        let selectedAU = auScales[auScales.length - 1]; // Default to largest (10 AU)
        
        for (let i = 0; i < auScales.length; i++) {
          const auScale = auScales[i];
          const widthPixels = EARTH_ORBIT_RADIUS_MAPUNITS * auScale.factor * pixelsPerMapUnit;
          const textWidth = ctx.measureText(auScale.label).width;
          
          // Check if text fits with padding
          if (textWidth + PADDING <= widthPixels) {
            selectedAU = auScale;
            break;
          }
        }
        
        barWidthPixels = Math.round(EARTH_ORBIT_RADIUS_MAPUNITS * selectedAU.factor * pixelsPerMapUnit);
        label = selectedAU.label;

      } else {
        // Calculate nanometers per pixel at this zoom level
        // At zoom 6, 1 pixel = 1 µm = 1000 nm
        // Each zoom level doubles/halves the scale
        const nanometersPerPixel = 1000 / Math.pow(2, zoom - parcel_zoom);

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
        
        // Create a temporary canvas to measure text width
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        ctx.font = '12px monospace'; // Match the scale bar font
        
        const PADDING = 16; // Space padding on each end (8px per side)

        // I know there must be a better (non-iterative) way to do this, but I give up. 
        
        // Find the smallest scale where the label fits inside the bar
        let selectedScale = scales[scales.length - 1]; // Default to largest (1m)
        
        for (let i = 0; i < scales.length; i++) {
          const scale = scales[i];
          const widthPixels = scale.nm / nanometersPerPixel;
          const textWidth = ctx.measureText(scale.label).width;
          
          // Check if text fits with padding
          if (textWidth + PADDING <= widthPixels) {
            selectedScale = scale;
            break;
          }
        }
        
        // Calculate the actual width in pixels for the selected scale
        barWidthPixels = Math.round(selectedScale.nm / nanometersPerPixel);
        label = selectedScale.label;
      }
      
      // Update the container width and text
      this._container.style.width = barWidthPixels + 'px';
      this._scaleText.textContent = label;
      
      // Show the control after updating (hidden during zoomstart)
      this._container.style.visibility = 'visible';
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
  // Note that the URL is not used but it has to be there or Leaflet will not load the tiles! (Ask me how i know)
  const debugLayer = new DebugTileLayer(  TILE_URL_TEMPLATE , {       
      tileSize: TILE_SIZE,  
      bounds: worldBounds,
      minNativeZoom: 0,
      maxNativeZoom: 6,
      minZoom: -7, 
      maxZoom: 10,        
      noWrap: true,
      updateWhenIdle: true,

  });

  // This is the main tile layer that shows the parcels. It will intionally fail to load tiles that are not found.
  // I think a 404 is faster than returning a 1px placeholder tile?

  const parcelsLayer = new L.TileLayer(  TILE_URL_TEMPLATE , {       
    tileSize: TILE_SIZE,  
    bounds: worldBounds,
    minNativeZoom: 0,   // The native sooms Are driven by how many tile sizes we have on the server (driven in build_world.py)
    maxNativeZoom: 6,   // This range covers 1 parcel pixel=1 tile  pixel out to where all parcels fit in a single tile. 
    minZoom: -2,        // Automatically hide parcels when zoomed out to solar system scale. 
    maxZoom: 10,        
    noWrap: true,
    // updateWhenIdle: true,  // The default seems right - yes for mobile, no for desktop
  });      

  // --- Gold disk circle
  
  // Create an overlay layer with a circle that represents the gold on the sapphire slide
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
    weight: 0,                      // Leaflet does not zoom border properly
    className: 'gold-disk-circle',
    fillOpacity: 1,     // Override Leaflet's default 0.2 opacity
    pane: 'goldDiskPane',  // Use custom pane to render behind tiles
    interactive: false,  // Don't capture mouse events
    //renderer: svgRenderer  // Explicitly use SVG renderer
  });
  
  circleLayer.addLayer(circle);

  // -- CWandT Layer
  
  // The following path was generated by a python program that converted the CW&T text in the Space Mono font to a polygon
  // as stolen from the cwandt homepage!

  var cwandLatlngs = [
    [[40.56627, -108.94148], [40.56451, -108.99376], [40.55926, -109.04642],
     [40.55050, -109.09946], [40.53823, -109.15288], [40.52246, -109.20669],
     [40.50319, -109.26087], [40.48041, -109.31544], [40.45413, -109.37039],
     [40.42434, -109.42572], [40.39105, -109.48143], [40.35425, -109.53752],
     [40.31395, -109.59400], [40.27015, -109.65086], [40.22284, -109.70809],
     [40.17203, -109.76571], [40.11771, -109.82371], [40.05989, -109.88209],
     [39.99856, -109.94086], [39.93373, -110.00000], [39.93208, -110.00000],
     [39.92711, -110.00000], [39.91882, -110.00000], [39.90723, -110.00000],
     [39.89231, -110.00000], [39.87409, -110.00000], [39.85255, -110.00000],
     [39.82770, -110.00000], [39.79953, -110.00000], [39.76805, -110.00000],
     [39.73326, -110.00000], [39.69515, -110.00000], [39.65373, -110.00000],
     [39.60900, -110.00000], [39.56095, -110.00000], [39.50959, -110.00000],
     [39.45492, -110.00000], [39.39693, -110.00000], [39.33563, -110.00000],
     [38.66437, -110.00000], [38.60303, -109.99844], [38.54132, -109.99375],
     [38.47921, -109.98595], [38.41673, -109.97502], [38.35387, -109.96096],
     [38.29063, -109.94379], [38.22700, -109.92349], [38.16299, -109.90007],
     [38.09860, -109.87352], [38.03383, -109.84386], [37.96868, -109.81106],
     [37.90315, -109.77515], [37.83723, -109.73612], [37.77094, -109.69396],
     [37.70426, -109.64867], [37.63720, -109.60027], [37.56976, -109.54874],
     [37.50194, -109.49409], [37.43373, -109.43632], [37.43373, -109.43495],
     [37.43373, -109.43083], [37.43373, -109.42398], [37.43373, -109.41438],
     [37.43373, -109.40205], [37.43373, -109.38697], [37.43373, -109.36915],
     [37.43373, -109.34859], [37.43373, -109.32529], [37.43373, -109.29924],
     [37.43373, -109.27046], [37.43373, -109.23893], [37.43373, -109.20466],
     [37.43373, -109.16765], [37.43373, -109.12790], [37.43373, -109.08541],
     [37.43373, -109.04017], [37.43373, -108.99220], [37.43373, -108.94148],
     [37.43455, -108.90489], [37.43698, -108.86758], [37.44103, -108.82956],
     [37.44670, -108.79082], [37.45400, -108.75136], [37.46291, -108.71120],
     [37.47345, -108.67031], [37.48561, -108.62871], [37.49939, -108.58640],
     [37.51479, -108.54337], [37.53181, -108.49963], [37.55045, -108.45517],
     [37.57071, -108.40999], [37.59260, -108.36410], [37.61610, -108.31750],
     [37.64123, -108.27018], [37.66798, -108.22214], [37.69634, -108.17339],
     [37.72633, -108.12392], [37.72770, -108.12326], [37.73182, -108.12125],
     [37.73867, -108.11792], [37.74827, -108.11324], [37.76060, -108.10724],
     [37.77568, -108.09989], [37.79350, -108.09122], [37.81406, -108.08120],
     [37.83736, -108.06986], [37.86341, -108.05718], [37.89219, -108.04316],
     [37.92372, -108.02781], [37.95799, -108.01112], [37.99500, -107.99310],
     [38.03475, -107.97374], [38.07724, -107.95305], [38.12248, -107.93102],
     [38.17045, -107.90766], [38.22117, -107.88296], [38.22202, -107.88296],
     [38.22456, -107.88296], [38.22879, -107.88296], [38.23471, -107.88296],
     [38.24233, -107.88296], [38.25164, -107.88296], [38.26264, -107.88296],
     [38.27533, -107.88296], [38.28972, -107.88296], [38.30580, -107.88296],
     [38.32357, -107.88296], [38.34303, -107.88296], [38.36419, -107.88296],
     [38.38704, -107.88296], [38.41158, -107.88296], [38.43782, -107.88296],
     [38.46575, -107.88296], [38.49537, -107.88296], [38.52668, -107.88296],
     [38.57831, -107.88296], [38.57831, -108.24441], [38.52668, -108.24441],
     [38.50544, -108.24524], [38.48339, -108.24684], [38.46053, -108.24920],
     [38.43685, -108.25232], [38.41237, -108.25621], [38.38708, -108.26086],
     [38.36097, -108.26627], [38.33406, -108.27244], [38.30633, -108.27938],
     [38.27780, -108.28708], [38.24845, -108.29554], [38.21830, -108.30477],
     [38.18733, -108.31475], [38.15555, -108.32551], [38.12297, -108.33702],
     [38.08957, -108.34930], [38.05536, -108.36234], [38.02034, -108.37614],
     [37.98451, -108.39071], [37.98391, -108.39155], [37.98213, -108.39409],
     [37.97915, -108.39832], [37.97497, -108.40425], [37.96961, -108.41186],
     [37.96305, -108.42117], [37.95531, -108.43217], [37.94637, -108.44487],
     [37.93624, -108.45925], [37.92491, -108.47533], [37.91240, -108.49311],
     [37.89869, -108.51257], [37.88379, -108.53373], [37.86770, -108.55658],
     [37.85042, -108.58112], [37.83194, -108.60735], [37.81227, -108.63528],
     [37.79141, -108.66490], [37.76936, -108.69621], [37.76936, -108.69689],
     [37.76936, -108.69893], [37.76936, -108.70233], [37.76936, -108.70708],
     [37.76936, -108.71320], [37.76936, -108.72067], [37.76936, -108.72950],
     [37.76936, -108.73970], [37.76936, -108.75125], [37.76936, -108.76415],
     [37.76936, -108.77842], [37.76936, -108.79405], [37.76936, -108.81103],
     [37.76936, -108.82938], [37.76936, -108.84908], [37.76936, -108.87014],
     [37.76936, -108.89256], [37.76936, -108.91634], [37.76936, -108.94148],
     [37.77077, -108.97817], [37.77499, -109.01486], [37.78202, -109.05154],
     [37.79187, -109.08823], [37.80453, -109.12492], [37.82000, -109.16161],
     [37.83828, -109.19830], [37.85938, -109.23499], [37.88329, -109.27167],
     [37.91001, -109.30836], [37.93955, -109.34505], [37.97190, -109.38174],
     [38.00706, -109.41843], [38.04504, -109.45511], [38.08582, -109.49180],
     [38.12943, -109.52849], [38.17584, -109.56518], [38.22507, -109.60187],
     [38.27711, -109.63855], [38.27825, -109.63855], [38.28169, -109.63855],
     [38.28741, -109.63855], [38.29542, -109.63855], [38.30572, -109.63855],
     [38.31830, -109.63855], [38.33318, -109.63855], [38.35034, -109.63855],
     [38.36979, -109.63855], [38.39154, -109.63855], [38.41556, -109.63855],
     [38.44188, -109.63855], [38.47049, -109.63855], [38.50139, -109.63855],
     [38.53457, -109.63855], [38.57004, -109.63855], [38.60780, -109.63855],
     [38.64785, -109.63855], [38.69019, -109.63855], [39.30981, -109.63855],
     [39.35613, -109.63759], [39.40269, -109.63469], [39.44948, -109.62986],
     [39.49652, -109.62311], [39.54379, -109.61442], [39.59130, -109.60380],
     [39.63905, -109.59125], [39.68704, -109.57676], [39.73526, -109.56035],
     [39.78373, -109.54201], [39.83243, -109.52173], [39.88137, -109.49953],
     [39.93055, -109.47539], [39.97997, -109.44932], [40.02963, -109.42132],
     [40.07952, -109.39139], [40.12966, -109.35953], [40.18003, -109.32574],
     [40.23064, -109.29002], [40.23064, -109.28905], [40.23064, -109.28616],
     [40.23064, -109.28133], [40.23064, -109.27457], [40.23064, -109.26588],
     [40.23064, -109.25526], [40.23064, -109.24271], [40.23064, -109.22823],
     [40.23064, -109.21181], [40.23064, -109.19347], [40.23064, -109.17319],
     [40.23064, -109.15099], [40.23064, -109.12685], [40.23064, -109.10078],
     [40.23064, -109.07279], [40.23064, -109.04286], [40.23064, -109.01099],
     [40.23064, -108.97720], [40.23064, -108.94148], [40.23004, -108.91548],
     [40.22825, -108.88913], [40.22527, -108.86242], [40.22110, -108.83535],
     [40.21574, -108.80792], [40.20918, -108.78014], [40.20143, -108.75200],
     [40.19249, -108.72350], [40.18236, -108.69464], [40.17104, -108.66543],
     [40.15852, -108.63585], [40.14482, -108.60592], [40.12992, -108.57564],
     [40.11383, -108.54499], [40.09654, -108.51399], [40.07807, -108.48263],
     [40.05840, -108.45091], [40.03754, -108.41884], [40.01549, -108.38640],
     [40.01454, -108.38601], [40.01168, -108.38483], [40.00691, -108.38286],
     [40.00023, -108.38011], [39.99165, -108.37657], [39.98116, -108.37224],
     [39.96877, -108.36713], [39.95446, -108.36123], [39.93825, -108.35454],
     [39.92013, -108.34707], [39.90011, -108.33881], [39.87818, -108.32976],
     [39.85434, -108.31993], [39.82859, -108.30931], [39.80094, -108.29790],
     [39.77138, -108.28571], [39.73991, -108.27273], [39.70654, -108.25896],
     [39.67126, -108.24441], [39.67071, -108.24441], [39.66906, -108.24441],
     [39.66632, -108.24441], [39.66248, -108.24441], [39.65755, -108.24441],
     [39.65152, -108.24441], [39.64439, -108.24441], [39.63617, -108.24441],
     [39.62684, -108.24441], [39.61643, -108.24441], [39.60491, -108.24441],
     [39.59230, -108.24441], [39.57859, -108.24441], [39.56379, -108.24441],
     [39.54789, -108.24441], [39.53089, -108.24441], [39.51280, -108.24441],
     [39.49361, -108.24441], [39.47332, -108.24441], [39.42169, -108.24441],
     [39.42169, -107.88296], [39.47332, -107.88296], [39.50601, -107.88363],
     [39.53974, -107.88563], [39.57452, -107.88897], [39.61035, -107.89364],
     [39.64723, -107.89965], [39.68515, -107.90699], [39.72413, -107.91567],
     [39.76416, -107.92568], [39.80523, -107.93703], [39.84735, -107.94971],
     [39.89053, -107.96373], [39.93475, -107.97908], [39.98002, -107.99577],
     [40.02634, -108.01379], [40.07371, -108.03315], [40.12212, -108.05384],
     [40.17159, -108.07586], [40.22210, -108.09923], [40.27367, -108.12392],
     [40.27448, -108.12524], [40.27691, -108.12917], [40.28096, -108.13572],
     [40.28663, -108.14490], [40.29393, -108.15670], [40.30284, -108.17113],
     [40.31338, -108.18817], [40.32554, -108.20784], [40.33932, -108.23013],
     [40.35472, -108.25504], [40.37174, -108.28257], [40.39038, -108.31273],
     [40.41064, -108.34551], [40.43253, -108.38091], [40.45603, -108.41893],
     [40.48116, -108.45958], [40.50791, -108.50284], [40.53628, -108.54873],
     [40.56627, -108.59725], [40.56627, -108.59820], [40.56627, -108.60106],
     [40.56627, -108.60583], [40.56627, -108.61250], [40.56627, -108.62109],
     [40.56627, -108.63157], [40.56627, -108.64397], [40.56627, -108.65827],
     [40.56627, -108.67448], [40.56627, -108.69260], [40.56627, -108.71263],
     [40.56627, -108.73456], [40.56627, -108.75840], [40.56627, -108.78414],
     [40.56627, -108.81180], [40.56627, -108.84136], [40.56627, -108.87282],
     [40.56627, -108.90620], [40.56627, -108.94148]],
    [[40.50602, -107.28916], [37.49398, -107.59466], [37.49398, -107.26764],
     [40.35112, -106.97935], [40.35112, -106.92771], [37.49398, -106.65663],
     [37.49398, -105.99398], [40.35112, -105.72289], [40.35112, -105.67126],
     [37.49398, -105.38296], [37.49398, -105.05594], [40.50602, -105.36145],
     [40.50602, -106.01979], [37.64888, -106.29948], [37.64888, -106.35112],
     [40.50602, -106.63081]],
    [[40.50602, -103.89415], [40.50478, -103.93953], [40.50107, -103.98507],
     [40.49487, -104.03078], [40.48619, -104.07666], [40.47503, -104.12270],
     [40.46140, -104.16892], [40.44528, -104.21529], [40.42669, -104.26184],
     [40.40561, -104.30855], [40.38206, -104.35543], [40.35603, -104.40248],
     [40.32752, -104.44969], [40.29653, -104.49707], [40.26306, -104.54462],
     [40.22711, -104.59233], [40.18868, -104.64021], [40.14777, -104.68826],
     [40.10439, -104.73647], [40.05852, -104.78485], [40.05758, -104.78485],
     [40.05475, -104.78485], [40.05005, -104.78485], [40.04345, -104.78485],
     [40.03498, -104.78485], [40.02462, -104.78485], [40.01238, -104.78485],
     [39.99825, -104.78485], [39.98225, -104.78485], [39.96436, -104.78485],
     [39.94458, -104.78485], [39.92292, -104.78485], [39.89938, -104.78485],
     [39.87396, -104.78485], [39.84665, -104.78485], [39.81746, -104.78485],
     [39.78639, -104.78485], [39.75343, -104.78485], [39.71859, -104.78485],
     [39.66695, -104.78485], [39.64129, -104.78403], [39.61503, -104.78156],
     [39.58818, -104.77745], [39.56073, -104.77169], [39.53268, -104.76429],
     [39.50404, -104.75525], [39.47480, -104.74455], [39.44497, -104.73222],
     [39.41454, -104.71824], [39.38351, -104.70261], [39.35189, -104.68534],
     [39.31967, -104.66642], [39.28685, -104.64586], [39.25344, -104.62365],
     [39.21944, -104.59980], [39.18484, -104.57431], [39.14964, -104.54717],
     [39.11384, -104.51838], [39.07745, -104.48795], [39.07730, -104.48737],
     [39.07683, -104.48562], [39.07606, -104.48270], [39.07497, -104.47861],
     [39.07358, -104.47335], [39.07187, -104.46693], [39.06986, -104.45933],
     [39.06754, -104.45057], [39.06490, -104.44064], [39.06196, -104.42955],
     [39.05870, -104.41728], [39.05514, -104.40385], [39.05127, -104.38925],
     [39.04708, -104.37348], [39.04259, -104.35654], [39.03778, -104.33843],
     [39.03267, -104.31916], [39.02725, -104.29872], [39.02151, -104.27711],
     [38.96988, -104.27711], [38.96278, -104.29954], [38.95415, -104.32245],
     [38.94399, -104.34584], [38.93231, -104.36970], [38.91910, -104.39404],
     [38.90437, -104.41885], [38.88811, -104.44415], [38.87033, -104.46992],
     [38.85102, -104.49616], [38.83018, -104.52289], [38.80782, -104.55009],
     [38.78394, -104.57776], [38.75852, -104.60592], [38.73159, -104.63455],
     [38.70312, -104.66366], [38.67313, -104.69324], [38.64162, -104.72330],
     [38.60858, -104.75384], [38.57401, -104.78485], [38.57333, -104.78485],
     [38.57129, -104.78485], [38.56790, -104.78485], [38.56314, -104.78485],
     [38.55703, -104.78485], [38.54955, -104.78485], [38.54072, -104.78485],
     [38.53053, -104.78485], [38.51898, -104.78485], [38.50607, -104.78485],
     [38.49180, -104.78485], [38.47618, -104.78485], [38.45919, -104.78485],
     [38.44085, -104.78485], [38.42114, -104.78485], [38.40008, -104.78485],
     [38.37766, -104.78485], [38.35388, -104.78485], [38.32874, -104.78485],
     [38.27711, -104.78485], [38.24147, -104.78358], [38.20521, -104.77975],
     [38.16833, -104.77338], [38.13083, -104.76445], [38.09271, -104.75297],
     [38.05398, -104.73894], [38.01462, -104.72236], [37.97464, -104.70323],
     [37.93404, -104.68155], [37.89282, -104.65732], [37.85099, -104.63053],
     [37.80853, -104.60120], [37.76545, -104.56931], [37.72176, -104.53488],
     [37.67744, -104.49789], [37.63250, -104.45836], [37.58695, -104.41627],
     [37.54077, -104.37163], [37.49398, -104.32444], [37.49398, -104.32325],
     [37.49398, -104.31967], [37.49398, -104.31371], [37.49398, -104.30537],
     [37.49398, -104.29464], [37.49398, -104.28153], [37.49398, -104.26604],
     [37.49398, -104.24816], [37.49398, -104.22789], [37.49398, -104.20525],
     [37.49398, -104.18022], [37.49398, -104.15280], [37.49398, -104.12300],
     [37.49398, -104.09082], [37.49398, -104.05625], [37.49398, -104.01930],
     [37.49398, -103.97997], [37.49398, -103.93825], [37.49398, -103.89415],
     [37.49398, -103.34337], [37.82960, -103.34337], [37.82960, -103.86833],
     [37.83031, -103.89480], [37.83242, -103.92168], [37.83593, -103.94897],
     [37.84086, -103.97665], [37.84719, -104.00475], [37.85492, -104.03325],
     [37.86406, -104.06215], [37.87461, -104.09146], [37.88657, -104.12118],
     [37.89993, -104.15130], [37.91470, -104.18182], [37.93087, -104.21276],
     [37.94845, -104.24409], [37.96744, -104.27583], [37.98783, -104.30798],
     [38.00964, -104.34053], [38.03284, -104.37349], [38.05746, -104.40685],
     [38.08348, -104.44062], [38.08408, -104.44062], [38.08591, -104.44062],
     [38.08895, -104.44062], [38.09320, -104.44062], [38.09867, -104.44062],
     [38.10536, -104.44062], [38.11326, -104.44062], [38.12238, -104.44062],
     [38.13272, -104.44062], [38.14427, -104.44062], [38.15703, -104.44062],
     [38.17101, -104.44062], [38.18621, -104.44062], [38.20262, -104.44062],
     [38.22025, -104.44062], [38.23910, -104.44062], [38.25916, -104.44062],
     [38.28043, -104.44062], [38.30293, -104.44062], [38.32874, -104.44062],
     [38.35330, -104.43979], [38.37804, -104.43728], [38.40298, -104.43311],
     [38.42810, -104.42727], [38.45342, -104.41976], [38.47893, -104.41058],
     [38.50463, -104.39974], [38.53052, -104.38722], [38.55660, -104.37304],
     [38.58287, -104.35718], [38.60933, -104.33966], [38.63598, -104.32047],
     [38.66282, -104.29961], [38.68986, -104.27708], [38.71708, -104.25289],
     [38.74449, -104.22702], [38.77210, -104.19949], [38.79990, -104.17029],
     [38.82788, -104.13941], [38.82788, -104.13870], [38.82788, -104.13655],
     [38.82788, -104.13298], [38.82788, -104.12797], [38.82788, -104.12154],
     [38.82788, -104.11367], [38.82788, -104.10437], [38.82788, -104.09364],
     [38.82788, -104.08149], [38.82788, -104.06790], [38.82788, -104.05288],
     [38.82788, -104.03643], [38.82788, -104.01855], [38.82788, -103.99924],
     [38.82788, -103.97850], [38.82788, -103.95633], [38.82788, -103.93273],
     [38.82788, -103.90770], [38.82788, -103.88124], [38.82788, -103.29174],
     [38.37177, -103.29174], [38.37177, -102.93029], [38.82788, -102.93029],
     [38.82788, -102.51291], [39.16351, -102.51291], [39.16351, -102.93029],
     [40.50602, -102.93029]],
    [[40.17040, -103.86833], [40.17040, -103.29174], [39.16351, -103.29174],
     [39.16351, -103.88124], [39.16427, -103.90853], [39.16656, -103.93607],
     [39.17038, -103.96384], [39.17572, -103.99185], [39.18258, -104.02010],
     [39.19097, -104.04859], [39.20089, -104.07731], [39.21233, -104.10628],
     [39.22530, -104.13548], [39.23980, -104.16492], [39.25582, -104.19460],
     [39.27336, -104.22452], [39.29243, -104.25468], [39.31303, -104.28507],
     [39.33515, -104.31570], [39.35880, -104.34658], [39.38397, -104.37768],
     [39.41067, -104.40903], [39.43890, -104.44062], [39.43953, -104.44062],
     [39.44143, -104.44062], [39.44458, -104.44062], [39.44901, -104.44062],
     [39.45469, -104.44062], [39.46164, -104.44062], [39.46985, -104.44062],
     [39.47933, -104.44062], [39.49007, -104.44062], [39.50207, -104.44062],
     [39.51534, -104.44062], [39.52987, -104.44062], [39.54566, -104.44062],
     [39.56272, -104.44062], [39.58104, -104.44062], [39.60062, -104.44062],
     [39.62147, -104.44062], [39.64358, -104.44062], [39.66695, -104.44062],
     [39.69277, -104.44062], [39.71641, -104.43973], [39.74021, -104.43704],
     [39.76418, -104.43257], [39.78832, -104.42632], [39.81262, -104.41827],
     [39.83709, -104.40844], [39.86173, -104.39682], [39.88653, -104.38341],
     [39.91151, -104.36821], [39.93664, -104.35122], [39.96195, -104.33245],
     [39.98742, -104.31189], [40.01306, -104.28954], [40.03886, -104.26540],
     [40.06484, -104.23948], [40.09098, -104.21177], [40.11728, -104.18227],
     [40.14376, -104.15098], [40.17040, -104.11790], [40.17040, -104.11721],
     [40.17040, -104.11513], [40.17040, -104.11168], [40.17040, -104.10684],
     [40.17040, -104.10062], [40.17040, -104.09301], [40.17040, -104.08403],
     [40.17040, -104.07366], [40.17040, -104.06190], [40.17040, -104.04877],
     [40.17040, -104.03425], [40.17040, -104.01835], [40.17040, -104.00107],
     [40.17040, -103.98240], [40.17040, -103.96235], [40.17040, -103.94092],
     [40.17040, -103.91811], [40.17040, -103.89391], [40.17040, -103.86833]],
    [[40.50602, -101.23924], [37.82960, -101.23924], [37.82960, -102.11704],
     [37.49398, -102.11704], [37.49398, -100.00000], [37.82960, -100.00000],
     [37.82960, -100.87780], [40.50602, -100.87780]]
  ];  

  var polygon = L.polygon(cwandLatlngs, {color: 'red'}).addTo(map);
  

  // --- Create grid line layer

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

  // Note that this will only ever remove the grid if we are zoomed out too far
  // it will not add it back if we then zoom back in. I am ok with that. 
  
  function updateGridVisibility() {
    const zoom = map.getZoom();
    const shouldBeVisible = zoom >= 0; // Show when at or above parcel minZoom

    if (!shouldBeVisible) {
      map.removeLayer(gridLayer);
    }
  }

  // --- Solar System Layer
  // Treat the gold disk as the sun and add planet orbits at scale
  
  // Create custom pane for solar system (above gold disk, below tiles)
  map.createPane('solarSystemPane');
  const solarPane = map.getPane('solarSystemPane');
  solarPane.style.zIndex = 175; // Between goldDisk (150) and tiles (200)
  
  const solarSystemLayer = L.layerGroup();
  
  // Solar system constants
  const SUN_DIAMETER_KM = 1392000; // Sun's diameter in km
  const DISK_DIAMETER_KM = disk_diameter_um / 1e9; // Convert disk from micrometers to km
  const SCALE_FACTOR = DISK_DIAMETER_KM / SUN_DIAMETER_KM; // Scale factor for orbits
  
  // NOTE: At true scale, the solar system is HUGE compared to the sun.
  // Mercury's orbit alone would be 40x the sun's diameter!
  // Apply an additional scale factor to fit orbits in the visible area.
  // With a factor of 0.01, orbits fit nicely: Mercury at ~160 units, Neptune at ~1260 units.
  const ORBIT_COMPRESSION = 0.5; // Compress orbits to make them visible
  
  // Planet data: orbital radius (million km), relative size, color, orbital period (Earth years)
  const planets = [
    { name: 'Mercury', orbitKm: 57.9e6, size: 0.38, color: '#8C7853', period: 0.24 },
    { name: 'Venus', orbitKm: 108.2e6, size: 0.95, color: '#FFC649', period: 0.62 },
    { name: 'Earth', orbitKm: 149.6e6, size: 1.0, color: '#4A90E2', period: 1.0 },
    { name: 'Mars', orbitKm: 227.9e6, size: 0.53, color: '#E27B58', period: 1.88 },
    { name: 'Jupiter', orbitKm: 778.5e6, size: 11.2, color: '#C88B3A', period: 11.86 },
    { name: 'Saturn', orbitKm: 1434e6, size: 9.45, color: '#FAD5A5', period: 29.46 },
    { name: 'Uranus', orbitKm: 2871e6, size: 4.0, color: '#4FD0E0', period: 84.01 },
    { name: 'Neptune', orbitKm: 4495e6, size: 3.88, color: '#4166F5', period: 164.79 }
  ];
  
  // Calculate base planet size (visible at zoom -4, scaled relatively)
  // At zoom -4, we want planets to be visible, so let's use map units
  const BASE_PLANET_RADIUS_MAPUNITS = 8; // Increased for better visibility
  
  // Store planet markers for animation
  const planetMarkers = [];
  
  // Calculate Earth's orbital radius for 1 AU scale reference
  // Find Earth in the planets array
  const earthData = planets.find(p => p.name === 'Earth');
  const earthOrbitRadiusKm = earthData.orbitKm * SCALE_FACTOR * ORBIT_COMPRESSION;
  const EARTH_ORBIT_RADIUS_MAPUNITS = (earthOrbitRadiusKm * 1e9) / UM_PER_MAPUNIT; // 1 AU in map units
  
  planets.forEach(planet => {
    // Calculate orbit radius in map units
    const orbitRadiusKm = planet.orbitKm * SCALE_FACTOR * ORBIT_COMPRESSION;
    const orbitRadiusMapUnits = (orbitRadiusKm * 1e9) / UM_PER_MAPUNIT; // Convert km to micrometers, then to map units
    
    // // Create orbit path (dim grey circle)
    // const orbitPath = L.circle([0, 0], {
    //   radius: orbitRadiusMapUnits,
    //   color: '#1f1f1f',
    //   fillOpacity: 0,
    //   weight: 2,
    //   opacity: 0.5,
    //   interactive: false,
    //   pane: 'solarSystemPane',
    //   renderer: svgRenderer
    // });
    // solarSystemLayer.addLayer(orbitPath);
    
    // Calculate planet display radius (relative to Earth, visible at zoom -4)
    const planetRadiusMapUnits = BASE_PLANET_RADIUS_MAPUNITS * planet.size;
    
    // Create planet marker (will be animated)
    const planetCircle = L.circle([0, orbitRadiusMapUnits], {
      radius: planetRadiusMapUnits+1,
      color: planet.color,
      fillColor: planet.color,
      fillOpacity: 0.9,
      weight: 0,                  // Fun fact: leaflet does not scale boreders properly durring zoom animations. :/
      opacity: 1,
      interactive: false,
      pane: 'solarSystemPane',
      renderer: svgRenderer
    });
    solarSystemLayer.addLayer(planetCircle);
    
    // Store for animation
    planetMarkers.push({
      circle: planetCircle,
      orbitRadius: orbitRadiusMapUnits,
      period: planet.period, // Earth years per orbit
      name: planet.name
    });

    // // Test: add a single planet directly, not in layer group
    // const testPlanet = L.circle([ 250 , 0], {
    //   radius: 8,
    //   color: '#ff00ff',
    //   fillColor: '#ff00ff',
    //   fillOpacity: 0.9,
    //   weight: 0,
    //   pane: 'goldDiskPane',  // Try gold disk pane
    //   renderer: svgRenderer
    // });
    // solarSystemLayer.addLayer(testPlanet);


  });
  
  // Animation: planets complete orbit in 1 minute (60 seconds)
  // Earth takes 60 seconds, other planets scale by their period
  let startTime = Date.now();
  let animationRunning = false;
  let pausedElapsed = 0; // Track elapsed time when paused
  
  function animatePlanets() {
    if (!animationRunning) return; // Stop if layer was removed
    
    const elapsed = (Date.now() - startTime) / 1000; // seconds elapsed

    //console.log("animate: elapsed=" + elapsed+  " zoom=" + map.getZoom());
    
    planetMarkers.forEach(planet => {
      // Earth completes 1 orbit in 60 seconds
      // Other planets: angle = (elapsed / 60) * (1 / planet.period) * 2π
      const earthOrbitsPerSecond = 1 / 60; // Earth completes 1 orbit per 60 seconds
      const planetOrbitsPerSecond = earthOrbitsPerSecond / planet.period;
      const angle = elapsed * planetOrbitsPerSecond * 2 * Math.PI;
      
      // Calculate position (counterclockwise from right/east)
      const x = planet.orbitRadius * Math.cos(angle);
      const y = planet.orbitRadius * Math.sin(angle);
      
      // Update planet position
      planet.circle.setLatLng([y, x]);
    });
    
    requestAnimationFrame(animatePlanets);
  }
  
  // Pause planet animation during zoom to avoid position conflicts with Leaflet's transform
  // Also pause "time" so planets resume from where they were, not where they "should be"
  // We have to do this becuase if you try to update Stuff inside layers asynchonously while the map is zooming, 
  // things get messed up and the animation gets all wonky. And if we just pause the animation durring the zooming, 
  // then when we resume the animation, the planets "jump" to make up lost time. This is pysically aweful, but
  // visually looks fine. 
  
  map.on('zoomstart', () => {
    if (animationRunning) {
      // Save the current elapsed time before pausing
      pausedElapsed = (Date.now() - startTime) / 1000;
      animationRunning = false;
    }
  });

  map.on('zoomend', () => {
    if (!animationRunning && pausedElapsed > 0) {
      // Resume time from where we paused: adjust startTime backward by the paused elapsed time
      startTime = Date.now() - (pausedElapsed * 1000);
      animationRunning = true;
      animatePlanets();
    }
  });
  
  // Set zoom range for solar system (only visible at far-out zoom levels)
  // We'll add/remove based on zoom level to control visibility
  let solarSystemVisible = false;
  
  function updateSolarSystemVisibility() {
    const zoom = map.getZoom();
    const shouldBeVisible = zoom <= -1; // Show when zoomed out beyond -1
    
    if (shouldBeVisible && !solarSystemVisible) {
      map.addLayer(solarSystemLayer);
      solarSystemVisible = true;
      animationRunning = true;
      animatePlanets();
    } else if (!shouldBeVisible && solarSystemVisible) {
      map.removeLayer(solarSystemLayer);
      solarSystemVisible = false;
      animationRunning = false;
    }
  }



 
  
  // Start/stop animation when layer is added/removed
  // Store original methods
  const originalOnAdd = solarSystemLayer.onAdd.bind(solarSystemLayer);
  const originalOnRemove = solarSystemLayer.onRemove.bind(solarSystemLayer);
  
  solarSystemLayer.onAdd = function(map) {
    // Call parent's onAdd to actually add layers to map
    originalOnAdd(map);
    
    if (!animationRunning) {
      animationRunning = true;
      animatePlanets();
    }
  };
  
  solarSystemLayer.onRemove = function(map) {
    animationRunning = false;
    
    // Call parent's onRemove to actually remove layers
    originalOnRemove(map);
  };

  // --- Parcel Labels Layer
  // Create labels for each parcel (A1 in lower left to AL38 in upper right)
  
  const labelsLayer = L.layerGroup();
  
  // Loop through all parcels in the 38x38 grid
  for (let row = 0; row < PARCEL_ROWS; row++) {
    for (let col = 0; col < PARCEL_COLS; col++) {
      // Generate parcel identifier (e.g., "A1", "B12", "AL38")
      const label = `${indexToLetters(row)}${col + 1}`;
      
      // Convert row/col to centered parcel coordinates
      const parcelX = col - PARCEL_COLS / 2;
      const parcelY = row - PARCEL_ROWS / 2;
      
      // Calculate position of lower-left corner of parcel in map units
      // Remember: y-axis is flipped, so "lower" means smaller y value
      const x = parcelX * mapunit_per_parceltile;
      const y = parcelY * mapunit_per_parceltile;
      
      // Create a DivIcon for the text label
      const icon = L.divIcon({
        className: 'parcel-label',
        html: label,
        iconSize: null,  // Let CSS control size
        iconAnchor: [0, 0]  // Anchor at top-left of icon (will be positioned at lower-left of parcel)
      });
      
      // Create marker at the lower-left corner of the parcel
      const marker = L.marker([y, x], {
        icon: icon,
        interactive: false  // Don't block map interactions
      });
      
      labelsLayer.addLayer(marker);
    }
  }


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
    "Grid Lines": gridLayer,
    //"Solar System": solarSystemLayer,   // peope should discover this, not see it in the menu!
    //"Parcel Labels": labelsLayer,   // Needs work
    "Status Display": statusControlLayer,    // not really neeeded anymore now that this info is in the URL
    "Scale Bar": scaleControlLayer,
    //"Debug Tiles": debugLayer,
  };
  
  // Create the layers control once (layers can be added dynamically later)
  const layersControl = L.control.layers([], overlayLayers, { 
    position: 'topright', 
    hideSingleBase: true 
  }).addTo(map);
  
  // Add default layers - gold disk first (behind), then parcels (on top)

  circleLayer.addTo(map);
  parcelsLayer.addTo(map);

  // Scale control is on by default
  scaleControlLayer.addTo(map);
  
  // --- URL-based View Sharing
  // Update URL to reflect current map view (similar to Google Maps)
  // Format: ?@lat,lng,radiusum where radius is in micrometers
  
  function updateURLFromView() {
    const center = map.getCenter();
    const bounds = map.getBounds();
    
    // Calculate the radius of the view in micrometers
    // Use the vertical extent (north-south) as the radius
    const viewHeightMapUnits = bounds.getNorth() - bounds.getSouth();
    const viewRadiusMapUnits = viewHeightMapUnits / 2;
    const viewRadiusMicrometers = viewRadiusMapUnits * UM_PER_MAPUNIT;
    
    // Format the view parameter value: lat,lng,radiusum
    const viewValue = `${center.lat.toFixed(2)},${center.lng.toFixed(2)},${viewRadiusMicrometers.toFixed(0)}um`;
    
    // Get current URL and build new query string manually to avoid encoding the @ and commas
    const url = new URL(window.location.href);
    const searchParams = new URLSearchParams(url.search);
    
    // Remove @ if it exists (we'll add it manually)
    searchParams.delete('@');
    
    // Build query string with @ parameter first (unencoded), then other params
    let queryString = `@=${viewValue}`;
    const otherParams = searchParams.toString();
    if (otherParams) {
      queryString += '&' + otherParams;
    }
    
    // Reconstruct URL with updated query parameters
    const newURL = url.origin + url.pathname + '?' + queryString + url.hash;
    
    // Update browser URL without reloading the page
    window.history.replaceState({}, '', newURL);
  }
  
  // Parse view from URL and restore it
  function restoreViewFromURL() {
    const urlParams = new URLSearchParams(window.location.search);
    const viewParam = urlParams.get('@');
    
    if (viewParam) {
      const match = viewParam.match(/^([-\d.]+),([-\d.]+),([\d.]+)um$/);
      
      if (match) {
        const lat = parseFloat(match[1]);
        const lng = parseFloat(match[2]);
        const radiusMicrometers = parseFloat(match[3]);
        
        if (Number.isFinite(lat) && Number.isFinite(lng) && Number.isFinite(radiusMicrometers)) {
          // Convert radius from micrometers to map units
          const radiusMapUnits = radiusMicrometers / UM_PER_MAPUNIT;
          
          // Create bounds centered at the specified point with the specified radius
          const bounds = L.latLngBounds(
            [lat - radiusMapUnits, lng - radiusMapUnits],  // Southwest corner
            [lat + radiusMapUnits, lng + radiusMapUnits]   // Northeast corner
          );
          
          // Fit the map to these bounds
          map.fitBounds(bounds);
          
          console.log(`Restored view from URL: center (${lat}, ${lng}), radius ${radiusMicrometers}um`);
          return true;
        }
      }
    }
    return false;
  }
  

  // --- Restore view from URL if present
  // Try to restore view from @ parameter in URL (takes precedence over parcel parameter if both present)
  // NOtew we need to do this here, before we process any parcel param so that the parcel param does not override the view param
  const viewRestored = restoreViewFromURL();

  // --- Parcel Highlighting from URL Parameter
  // Check for ?parcel=AA4 style parameter in URL and highlight if present

  // Parcel highlight visibility: hide when zoomed out past parcel layer minZoom (-2)
  let highlightLayer = null; // Will be set if parcel parameter is present
  let highlightVisible = false;  
  
  const urlParams = new URLSearchParams(window.location.search);
  const highlightParcelId = urlParams.get('parcel');
  
  if (highlightParcelId) {
    const parsed = parseCoord(highlightParcelId);
    
    if (parsed && parsed.row >= 0 && parsed.row < PARCEL_ROWS && parsed.col >= 0 && parsed.col < PARCEL_COLS) {
      // Convert row/col to centered parcel coordinates
      const parcelX = parsed.col - PARCEL_COLS / 2;
      const parcelY = parsed.row - PARCEL_ROWS / 2;
      
      // Calculate the parcel bounds in map units
      const x0 = parcelX * mapunit_per_parceltile;
      const y0 = parcelY * mapunit_per_parceltile;
      const x1 = x0 + mapunit_per_parceltile;
      const y1 = y0 + mapunit_per_parceltile;
      
      // Create a rectangle with blue 3px border to highlight the parcel
      const highlightRect = L.rectangle(
        [[y0, x0], [y1, x1]],  // Leaflet expects [[lat, lng], [lat, lng]]
        {
          color: '#0066ff',      // Blue border
          weight: 3,             // 3px border width
          fillOpacity: 0,        // No fill, just the border
          interactive: false,    // Don't block map interactions
          renderer: svgRenderer  // Use SVG renderer for crisp lines
        }
      );
      
      // Create a layer group for the highlight
      highlightLayer = L.layerGroup(); // Use global variable
      highlightLayer.addLayer(highlightRect);
      
      // Add the highlight layer to the map by default
      highlightLayer.addTo(map);
      highlightVisible = true; // Track that it's visible
      
      // Dynamically add the highlight layer to the existing layers control

      const parcelLayerURL = `/?parcel=${highlightParcelId}`;

      layersControl.addOverlay(highlightLayer, `Highlight <a href="${parcelLayerURL}">${highlightParcelId}</a>`);

      console.log(`Highlighting parcel ${highlightParcelId} at row ${parsed.row}, col ${parsed.col}`);

      // If no view was specified in the URL, then lets fram the selected parcel into view

      if (!viewRestored) {
        
        // Calculate bounds with 10% margin around the parcel
        const parcelWidth = mapunit_per_parceltile;
        const parcelHeight = mapunit_per_parceltile;
        const margin = 0.1;  // 10% margin
        
        const boundsX0 = x0 - parcelWidth * margin;
        const boundsY0 = y0 - parcelHeight * margin;
        const boundsX1 = x1 + parcelWidth * margin;
        const boundsY1 = y1 + parcelHeight * margin;
        
        const highlightBounds = L.latLngBounds(
          [[boundsY0, boundsX0],  // Southwest corner
          [boundsY1, boundsX1]]   // Northeast corner
        );
        
        // Fit the map to show the highlighted parcel with margin
        map.fitBounds(highlightBounds);
        console.log(`Fitting map view to highlight bounds: ${highlightBounds}`);
      }

    } else {
      console.warn(`Invalid parcel ID in URL: ${highlightParcelId}`);
    }
  }
   
  function updateHighlightVisibility() {
    if (!highlightLayer) return; // No highlight layer to manage
    
    const zoom = map.getZoom();
    const shouldBeVisible = zoom >= 0; // Show when at or above parcel minZoom
    
    if (shouldBeVisible && !highlightVisible) {
      highlightLayer.addTo(map);
      highlightVisible = true;
    } else if (!shouldBeVisible && highlightVisible) {
      map.removeLayer(highlightLayer);
      highlightVisible = false;
    }
  }

  // Note: layers control is already created above, no need to create it here

  // Listen for pan/zoom completion and update URL
  map.on('moveend zoomend', () => {
    // Use a small debounce to avoid excessive updates during animations
    if (updateURLFromView.timeout) {
      clearTimeout(updateURLFromView.timeout);
    }
    updateURLFromView.timeout = setTimeout(updateURLFromView, 100);
  });
  
  
  // if (!viewRestored) {
  //   // No @ view parameter in URL, update URL to reflect current view
  //   // (whether from parcel parameter or default view)
  //   updateURLFromView();
  // }

  // Check if gridlines should be shown based on URL parameter
  const showGridlines = urlParams.get('gridlines') === 'on';
  if (showGridlines) {
    // Evaluate grid visibility based on zoom level
    map.addLayer(gridLayer);
  }

  // --- Zoom-based transitions for gold disk color
  // As we zoom out past -2, transition disk from gold (fiche) to orange (sun)
  
  // Helper function to interpolate between two hex colors
  function interpolateColor(color1, color2, factor) {
    // Parse hex colors
    const c1 = parseInt(color1.slice(1), 16);
    const c2 = parseInt(color2.slice(1), 16);
    
    const r1 = (c1 >> 16) & 0xff;
    const g1 = (c1 >> 8) & 0xff;
    const b1 = c1 & 0xff;
    
    const r2 = (c2 >> 16) & 0xff;
    const g2 = (c2 >> 8) & 0xff;
    const b2 = c2 & 0xff;
    
    // Interpolate
    const r = Math.round(r1 + (r2 - r1) * factor);
    const g = Math.round(g1 + (g2 - g1) * factor);
    const b = Math.round(b1 + (b2 - b1) * factor);
    
    // Convert back to hex
    return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
  }
  

  const goldColor   = '#af8149';   
  const cwandtColor = '#ff9412';    
  const sunColor    = "#FFCF37";

  // these transitions are imperically derived so sue me

  function diskColor( zoom ) {

    if (zoom >= 0) {
      // Just normal parcel views
      return goldColor;
    }

    // Once we get lower than zero, they zoomed out paste where the whole disk fills the canvas

    // gridlines should disapear at -1

    // Stuff in the disk should disapear at -2

    // when we get to -3 we should be cwt

    if (zoom == -1 ) {
      return interpolateColor(goldColor, cwandtColor, 0.33);
    }

    if (zoom == -2 ) {
      return interpolateColor(goldColor, cwandtColor, 0.66);
    }

    if (zoom == -3 ) {
      return cwandtColor;
    }

    if (zoom == -4 ) {
      return interpolateColor(cwandtColor, sunColor, 0.33);
    }

    if (zoom == -5 ) {
      return interpolateColor(cwandtColor, sunColor, 0.66);
    }

    return sunColor;

  }
    

  function updateDiskColor() {
    const zoom = map.getZoom();
    const newColor = diskColor(zoom);
    
    // Update the circle fill color directly
    if (circle._path) {
      circle._path.style.fill = newColor;
    }
  }
  
  function zoomChanged() {
    updateHighlightVisibility();
    updateGridVisibility();
    updateSolarSystemVisibility();
    updateDiskColor();
  }

  map.on('zoom', zoomChanged);

  // Initialize eveerything right to get started. 
  zoomChanged();
  

})();
