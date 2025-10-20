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

  // This is where the CW&T logo shows, and the disk will be cw&t organge.
  // This is a good level to make the logo appear becuase we know that the logo will fit int he viewport below the disk
  // and we are zoomed out pasty where seeeing the parcles is useful.
  const CWANT_LOGO_ZOOM_LEVEL = -2;    

  // After zoom 6, we are just scaling images, but let the people have thier fun
  // maybe some day we will put something interesting down here. 
  const MAP_MAX_ZOOM = 11;

  const MAP_MIN_ZOOM = -7;

  const COPYRIGHT_BANNER_MAX_ZOOM_LEVEL = MAP_MIN_ZOOM;

  // --- calculate constants to help with layout

  const mapunit_per_parceltile = mapunit_per_worldtile / parcels_per_world_ratio 

  const UM_PER_MAPUNIT =  (um_per_parcel_pixel * PIXELS_PER_PARCELTILE) / mapunit_per_parceltile 

  console.log("UM_PER_MAPUNIT", UM_PER_MAPUNIT);

  // Where to find the tiles (relative to the html file)
  const TILE_URL_TEMPLATE = "world/images/{z}/{x}/{y}.png";

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
  // Parse parcel names like "A1", "B5", "AL38"
  // - Letters (A, B, ..., Z, AA, AB, ..., AL) represent Y axis (vertical), incrementing north (up)
  // - Numbers (1, 2, 3, ..., 38) represent X axis (horizontal), incrementing east (right)
  // - A1 is at bottom-left corner
  // Tolerates an optional embedded ":" to match the format used in the kickstarter campaign
  function parseParceName(name) {
    // Make case-insensitive by converting to uppercase
    const normalizedCoord = name.toUpperCase().trim().replace(':', '');
    const m = /^([A-Z]+)(\d+)$/.exec(normalizedCoord);
    if (!m) return null;
    const letters = m[1];
    const xNum = parseInt(m[2], 10);
    if (!Number.isFinite(xNum)) return null;
    const yIdx = lettersToIndex(letters);  // Letters = Y axis
    if (yIdx == null) return null;

    // Letters map to Y index (vertical position, A=0, B=1, ..., AL=37)
    // Numbers map to X index (horizontal position, 1-based). Convert to 0-based.
    const xIdx = xNum - 1;
    return { row: yIdx, col: xIdx, letters, number: xNum };
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
        <style>
          @keyframes marching-ants {
            to { stroke-dashoffset: -10; }
          }
          .animated-dash {
            animation: marching-ants 0.5s linear infinite;
          }
        </style>
        <rect x="0" y="0" width="${w}" height="${h}" fill="none" stroke="#00000080" stroke-width="1" stroke-dasharray="5,5" class="animated-dash"/>
        <g font-family="monospace" fill="#80000080" stroke="#00000080" stroke-width="1">
          <text x="${w / 2}" y="36" font-size="24" text-anchor="middle">
            z=${coords.z}
            x=${coords.x}
            y=${coords.y}
          </text>
          <text x="${w / 2}" y="${h / 2}" font-size="64" text-anchor="middle" dominant-baseline="middle">${title}</text>
          <g stroke="#00000080" stroke-width="1" fill="#80000080">
            <line x1="0" y1="0" x2="${w}" y2="${h}" stroke-dasharray="5,5" class="animated-dash" />
            <line x1="${w}" y1="0" x2="0" y2="${h}" stroke-dasharray="5,5" class="animated-dash" />
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
    minZoom: MAP_MIN_ZOOM,
    maxZoom: MAP_MAX_ZOOM,
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


  // --- Status Control. Shows where you are in the world. (not really needed now that the location and zoom are in the URL)

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

  // Create a wrapper layer for the status control so it can be toggled
  const statusControlLayer = L.layerGroup();
  statusControlLayer.onAdd = function(map) {
    map.addControl(statusControl);
  };
  statusControlLayer.onRemove = function(map) {
    map.removeControl(statusControl);
  };


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

      // Scale bar ranges by zoom level
      switch (true) {
        case (zoom === CWANT_LOGO_ZOOM_LEVEL):
          // ===== CW&T SCALE (disk diameter) =====
          // Disk diameter in map units (already calculated globally)
          const diskDiameterMapUnits = radiusMapUnits * 2;
          // Convert map units to pixels at current zoom (at zoom 0, 1 map unit = 1 pixel)
          const pixelsPerMapUnit = Math.pow(2, zoom);
          barWidthPixels = diskDiameterMapUnits * pixelsPerMapUnit;
          label = '1CWT';
          break;
          
        case (zoom < CWANT_LOGO_ZOOM_LEVEL):
          // ===== ASTRONOMICAL UNIT SCALE (solar system) =====
          {
            // Calculate pixels per map unit at current zoom
            // At zoom 0, 1 map unit = 1 pixel
            // At zoom -1, 1 map unit = 0.5 pixels (zoomed out 2x)
            const pixelsPerMapUnit = Math.pow(2, zoom);
            
            // Define available AU scales
            const auScales = [
              { factor: 0.00001, label: '0.00001AU' },
              { factor: 0.0001,  label: '0.0001AU' },
              { factor: 0.001,   label: '0.001AU' },
              { factor: 0.01,    label: '0.01AU' },
              { factor: 0.1,     label: '0.1AU' },
              { factor: 1.0,     label: '1AU' },
              { factor: 10.0,    label: '10AU' }
            ];
            
            // Create a temporary canvas to measure text width
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            ctx.font = '12px monospace';
            
            const PADDING = 16;
            
            // Find the smallest AU scale where the label fits inside the bar
            let selectedAU = auScales[auScales.length - 1]; // Default to largest (10 AU)
            
            for (let i = 0; i < auScales.length; i++) {
              const auScale = auScales[i];
              const widthPixels = EARTH_ORBIT_RADIUS_MAPUNITS * auScale.factor * pixelsPerMapUnit;
              const textWidth = ctx.measureText(auScale.label).width;
              
              if (textWidth + PADDING <= widthPixels) {
                selectedAU = auScale;
                break;
              }
            }
            
            barWidthPixels = Math.round(EARTH_ORBIT_RADIUS_MAPUNITS * selectedAU.factor * pixelsPerMapUnit);
            label = selectedAU.label;
          }
          break;
          
        default:
          // This is the normal viewer scale
          // ===== MICROMETER SCALE (parcel/fiche scale) =====
          {
            // Calculate nanometers per pixel at this zoom level
            // At zoom 6, 1 pixel = 1 µm = 1000 nm
            const nanometersPerPixel = 1000 / Math.pow(2, zoom - parcel_zoom);

            // Define available scale sizes (all in nanometers)
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
            ctx.font = '12px monospace';
            
            const PADDING = 16;
            
            // Find the smallest scale where the label fits inside the bar
            let selectedScale = scales[scales.length - 1]; // Default to largest (1m)
            
            for (let i = 0; i < scales.length; i++) {
              const scale = scales[i];
              const widthPixels = scale.nm / nanometersPerPixel;
              const textWidth = ctx.measureText(scale.label).width;
              
              if (textWidth + PADDING <= widthPixels) {
                selectedScale = scale;
                break;
              }
            }
            
            barWidthPixels = Math.round(selectedScale.nm / nanometersPerPixel);
            label = selectedScale.label;
          }
          break;
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
    minNativeZoom: 0,                 // The native sooms Are driven by how many tile sizes we have on the server (driven in build_world.py)
    maxNativeZoom: 6,                 // This range covers 1 parcel pixel=1 tile  pixel out to where all parcels fit in a single tile. 
    minZoom: CWANT_LOGO_ZOOM_LEVEL+1, // Automatically hide parcels at and below the logo zoom level. 
    maxZoom: MAP_MAX_ZOOM,        
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
  
  // Disk color constants for different zoom levels
  const goldColor   = '#b78727';   // Default gold color at parcel zoom - "University of California Gold"
  const cwandtColor = '#ff9412';   // CW&T orange at intermediate zoom
  const sunColor    = '#FFDF22';   // "Sun yellow" at solar system zoom
  
  // Create circle centered at origin (0, 0)
  // Default to gold color (will be updated dynamically based on zoom)
  const circle = L.circle([0, 0], {
    radius: radiusMapUnits,
    weight: 0,                      // Leaflet does not zoom border properly
    fillColor: goldColor,           // Default gold color
    fillOpacity: 1,                 // Override Leaflet's default 0.2 opacity
    pane: 'goldDiskPane',           // Use custom pane to render behind tiles
    interactive: false,             // Don't capture mouse events
    //renderer: svgRenderer  // Explicitly use SVG renderer
  });
  
  circleLayer.addLayer(circle);


  // --- CW&T Logo Control
  // After so much effort, I finally found a way to position the svg in the viewport and still haev access to the element
  // so we can use a transition to fade it in and out while the map is zooming. If you think you can do this better with an overly
  /// good luck. 

  // Let's put it into a immediate function to hide the messyness. All we need to remeber is the container variable
  // so we can update the opacity and location of the svg element when we hit the zoom level where we want to show it.

  // We the svg inside div element and make it hidden. Then we will add it to the map container and move it to where it belongs when we hit the zoom level and then make it visible. 

  const cwandtLogoSvgDiv = (function() {

    // If youj ever need the CWT logo as a tight SVG... here you go! (generated by exporting simplified SVG from inkscape)
    const cwtSVG = `
      <svg viewBox="49 53 6 3" aria-label="CW and T lovel logo text">
      <g fill="#ffffffff" >
        <path d="m49.909 55.049q0.09102 0 0.15452-0.02963 0.06562-0.03175 0.10583-0.08255 0.04233-0.05292 0.06138-0.11853 0.02117-0.06773 0.02117-0.14182v-0.0254h0.1778v0.0254q0 0.11218-0.03387 0.21167-0.03387 0.09737-0.09948 0.17145-0.06562 0.07197-0.16298 0.1143-0.09737 0.04022-0.22437 0.04022-0.24553 0-0.38312-0.15452-0.13758-0.15452-0.13758-0.45085v-0.3302q0-0.28787 0.13758-0.44662 0.13758-0.15875 0.38312-0.15875 0.127 0 0.22437 0.04233 0.09737 0.04022 0.16298 0.1143 0.06562 0.07197 0.09948 0.17145 0.03387 0.09737 0.03387 0.20955v0.0254h-0.1778v-0.0254q-0.0021-0.07197-0.02328-0.1397-0.01905-0.06773-0.06138-0.11853-0.04022-0.05292-0.10372-0.08255-0.0635-0.03175-0.15452-0.03175-0.17145 0-0.25823 0.12488-0.08467 0.12488-0.08467 0.32808v0.3048q0 0.21802 0.08467 0.33655 0.08678 0.11642 0.25823 0.11642z"/>
        <path d="m51.668 55.185h-0.32385l-0.13758-1.4055h-0.0254l-0.13758 1.4055h-0.32385l-0.15028-1.4817h0.16087l0.14182 1.4055h0.0254l0.13335-1.4055h0.32597l0.13335 1.4055h0.0254l0.14182-1.4055h0.16087z"/>
        <path d="m53.068 54.524h-0.20532v0.6604h-0.47413q-0.10583 0-0.18838-0.02963t-0.13758-0.08043q-0.05503-0.05292-0.08467-0.12277-0.02752-0.07197-0.02752-0.15452v-0.0254q0-0.12065 0.07197-0.2032 0.07197-0.08467 0.1778-0.1143v-0.0254q-0.10583-0.02752-0.1778-0.11007-0.07197-0.08467-0.07197-0.20532v-0.0254q0-0.08255 0.02752-0.1524 0.02963-0.07197 0.08467-0.12277 0.05503-0.0508 0.13758-0.08043 0.08255-0.02963 0.18838-0.02963h0.27093v0.1651h-0.25823q-0.12488 0-0.2032 0.0635-0.07832 0.06138-0.07832 0.16933v0.0127q0 0.1143 0.07408 0.17992 0.07408 0.06562 0.20108 0.06562h0.28998v-0.22437h0.1778v0.22437h0.20532zm-0.38312 0.4953v-0.4953h-0.28998q-0.127 0-0.20108 0.06773-0.07408 0.06562-0.07408 0.17992v0.0127q0 0.11007 0.07832 0.17357 0.07832 0.06138 0.2032 0.06138z"/>
        <path d="m53.262 53.703h1.0414v0.1651h-0.4318v1.3166h-0.1778v-1.3166h-0.4318z"/>
      </g>
      </svg>
    `;

    // Parse SVG string into element
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = cwtSVG;
    const svgElement = tempDiv.firstElementChild;  // Get the <svg> element. There must be a better way, right?
    
    // Style the SVG to fill the div
    svgElement.style.display = 'block';
    svgElement.style.width = '100%';
    svgElement.style.height = '100%';
    
    // Create a container div to hold the SVG (not a link, just decorative)
    const container = document.createElement('div');
    container.appendChild(svgElement);
    container.style.position = 'absolute';
    container.style.transition = 'opacity 0.25s ease-in-out';
    container.style.pointerEvents = 'none';  // Never intercept clicks
    container.style.zIndex = '1000';  // Above map tiles (200) and overlays (400)
    container.style.opacity = 0;
    return container;

  })();

  // Here we add the svg to the map container
  // I wanted to only add it when we needed it, but then it is a pain becuase we want it to fade out when we leave the zoom level
  // so we cant remove it until after the fade finished asynchronously and then one if they fade back in again... so it is always hanging around.
  map.getContainer().appendChild(cwandtLogoSvgDiv);

  // --- Solar System Layer
  // Treat the gold disk as the sun and add planet orbits at scale

  const solarSystemLayer = L.layerGroup();
  
  // Create custom pane for solar system (above gold disk, below tiles)
  map.createPane('solarSystemPane');
  const solarPane = map.getPane('solarSystemPane');
  solarPane.style.zIndex = 175; // Between goldDisk (150) and tiles (200)
  

  
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
    
    // Show/hide copyright banner at solar system zoom level
    const copyrightBanner = document.getElementById('copyright-banner');
    if (copyrightBanner) {
      copyrightBanner.style.opacity = shouldBeVisible ? '1' : '0';
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

  // --- Parcel Labels Layer (Tile-based)
  // Load parcel labels from pre-generated tiles created by build_world.py
  // Labels are baked into tiles with text and grid borders
  
  // Create a custom pane for parcel labels so they render ABOVE main tiles
  map.createPane('parcelLabelsPane');
  map.getPane('parcelLabelsPane').style.zIndex = 250;
  
  const parcelLabelsLayer = new L.TileLayer('world/labels/{z}/{x}/{y}.png', {       
    tileSize: TILE_SIZE,  
    bounds: worldBounds,
    minNativeZoom: 0,
    maxNativeZoom: 6,
    minZoom: 0,
    maxZoom: MAP_MAX_ZOOM,        
    noWrap: true,
    pane: 'parcelLabelsPane',
    opacity: 0.6  // 60% opacity for subtle labels
  });


  
  // Create a wrapper layer for the scale control so it can be toggled
  const scaleControlLayer = L.layerGroup();
  scaleControlLayer.onAdd = function(map) {
    map.addControl(scaleControl);
  };
  scaleControlLayer.onRemove = function(map) {
    map.removeControl(scaleControl);
  };
  
  const overlayLayers = {
    //"Solar System": solarSystemLayer,   // people should discover this, not see it in the menu!
    "Parcel Labels": parcelLabelsLayer,
    // "Status Display": statusControlLayer,    // not really needed anymore now that this info is in the URL
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
  //cwandtImageOverlayMarker.addTo(map);
  
  // Get the actual logo image element that Leaflet inserted into the DOM
  //const cwandtLogoImgInDOM = cwandtImageOverlayMarker._icon?.querySelector('.cwandt-logo-icon');
  //console.log("Logo img in DOM:", cwandtLogoImgInDOM);
  
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
    const parsed = parseParceName(highlightParcelId);
    
    if (parsed && parsed.row >= 0 && parsed.row < PARCEL_ROWS && parsed.col >= 0 && parsed.col < PARCEL_COLS) {
      // Convert to parcel coordinates centered at origin
      // Letters (A-AL) = Y axis (vertical), north (up): parsed.row = 0 to 37
      // Numbers (1-38) = X axis (horizontal), east (right): parsed.col = 0 to 37
      // A1 is at bottom left: row=0, col=0 → X=-19, Y=-19
      // With 38 parcels, they span from -19 to +19 in parcel units
      const parcelX = parsed.col - PARCEL_COLS / 2;  // col 0 (1) → X=-19, col 37 (38) → X=+18
      const parcelY = parsed.row - PARCEL_ROWS / 2;  // row 0 (A) → Y=-19, row 37 (AL) → Y=+18
      
      // Calculate the parcel bounds in map units
      const x0 = parcelX * mapunit_per_parceltile;
      const x1 = x0 + mapunit_per_parceltile;
      const y0 = parcelY * mapunit_per_parceltile;  // Bottom edge
      const y1 = y0 + mapunit_per_parceltile;  // Top edge
      
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

  function updateCopyrightBannerVisiblility() {
    // Show/hide copyright banner at solar system zoom level
    const shouldBeVisible = map.getZoom() <= COPYRIGHT_BANNER_MAX_ZOOM_LEVEL;
    const copyrightBanner = document.getElementById('copyright-banner');
    if (copyrightBanner) {
      copyrightBanner.style.opacity = shouldBeVisible ? '1' : '0';
    }    
  }    
    
  // --- Click to Zoom to Parcel
  // When user clicks/taps on the map, check if they clicked inside a parcel
  // If so, zoom to fit that parcel with 10% margin
  
  // Extract zoom-to-parcel logic into a function for reuse with both click and tap events
  function handleParcelZoom(e) {
    // Get click coordinates in map units
    const clickY = e.latlng.lat;  // In Leaflet CRS.Simple, lat = Y
    const clickX = e.latlng.lng;  // lng = X
    
    // Convert map coordinates to parcel row/col
    // Parcels are centered at origin, spanning from -19 to +18 in parcel units
    const parcelX = clickX / mapunit_per_parceltile;  // X in parcel units
    const parcelY = clickY / mapunit_per_parceltile;  // Y in parcel units
    
    // Convert to parcel indices (0-37)
    const col = Math.floor(parcelX + PARCEL_COLS / 2);  // X=-19 → col=0, X=+18 → col=37
    const row = Math.floor(parcelY + PARCEL_ROWS / 2);  // Y=-19 → row=0, Y=+18 → row=37
    
    // Check if click is within valid parcel bounds
    if (row >= 0 && row < PARCEL_ROWS && col >= 0 && col < PARCEL_COLS) {
      // Convert row/col back to parcel center coordinates
      const parcelCenterX = (col - PARCEL_COLS / 2 + 0.5) * mapunit_per_parceltile;
      const parcelCenterY = (row - PARCEL_ROWS / 2 + 0.5) * mapunit_per_parceltile;
      
      // Calculate parcel bounds in map units
      const x0 = parcelCenterX - mapunit_per_parceltile / 2;
      const x1 = parcelCenterX + mapunit_per_parceltile / 2;
      const y0 = parcelCenterY - mapunit_per_parceltile / 2;
      const y1 = parcelCenterY + mapunit_per_parceltile / 2;
      
      // Add 10% margin
      const margin = 0.1;
      const parcelWidth = mapunit_per_parceltile;
      const parcelHeight = mapunit_per_parceltile;
      
      const boundsX0 = x0 - parcelWidth * margin;
      const boundsY0 = y0 - parcelHeight * margin;
      const boundsX1 = x1 + parcelWidth * margin;
      const boundsY1 = y1 + parcelHeight * margin;
      
      const parcelBounds = L.latLngBounds(
        [[boundsY0, boundsX0],  // Southwest corner
         [boundsY1, boundsX1]]   // Northeast corner
      );
      
      // Fit the map to show the parcel with margin
      map.fitBounds(parcelBounds);
      
      // Generate parcel name for logging
      const parcelName = indexToLetters(row) + (col + 1);
      console.log(`Clicked on parcel ${parcelName} (row ${row}, col ${col})`);
    }
  }
  
  // Register handler for both click (mouse) and tap (touch) events
  map.on('click', handleParcelZoom);
  map.on('tap', handleParcelZoom);

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


  // Check if debug mode should be enabled based on URL parameter
  const debugMode = urlParams.get('debug') === 'true';
  if (debugMode) {
    // Add debug layer to map and layer control
    debugLayer.addTo(map);
    layersControl.addOverlay(debugLayer, "Debug Tiles");
  }

  // Check if parcel names should be shown based on URL parameter
  const showNames = urlParams.get('names') === 'true';
  if (showNames) {
    parcelLabelsLayer.addTo(map);
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
  
  // Color constants are defined earlier near circle creation (lines ~511-513)

  function diskColor( zoom ) {

    if (zoom >= 0) {
      // At or above parcel zoom: gold color
      return goldColor;
    }

    // Zoom < 0: smooth color transitions as we zoom out
    
    if (zoom > CWANT_LOGO_ZOOM_LEVEL) {
      // Between 0 and CWANT_LOGO_ZOOM_LEVEL (-2): fade from gold to CW&T orange
      // Calculate factor: at zoom=0 factor=0 (gold), at zoom=-2 factor=1 (cwandt)
      const factor = -zoom / Math.abs(CWANT_LOGO_ZOOM_LEVEL);
      return interpolateColor(goldColor, cwandtColor, factor);
    }
    
    if (zoom > MAP_MIN_ZOOM) {
      // Between CWANT_LOGO_ZOOM_LEVEL (-2) and MAP_MIN_ZOOM (-7): fade from CW&T orange to sun yellow
      // Calculate factor: at zoom=-2 factor=0 (cwandt), at zoom=-7 factor=1 (sun)
      const range = MAP_MIN_ZOOM - CWANT_LOGO_ZOOM_LEVEL;  // -7 - (-2) = -5
      const offset = zoom - CWANT_LOGO_ZOOM_LEVEL;         // e.g., -4 - (-2) = -2
      const factor = -offset / Math.abs(range);             // e.g., -(-2) / 5 = 0.4
      return interpolateColor(cwandtColor, sunColor, factor);
    }
    
    // At or below MAP_MIN_ZOOM (-7): full sun color
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
    updateSolarSystemVisibility();
    updateDiskColor();
    updateCopyrightBannerVisiblility();
    //updateCwandtImageVisibility();  
  }

  map.on('zoom', zoomChanged);
  // Initialize everything right to get started. 
  zoomChanged();

  // ---- Special handling for the cwandt logo zoom level

  // For the cwandt layer things here are a bit different becuase we want the logo to fade in *after* we land on the
  // zoom level and fade out *before* we zoom to the next level. So we have to specifically catch the start and end events

  // This is overly complicated becuase leaflet doewsn't give us access to the underlying image element so we had to make 
  // a special DIV that alwazys lives above the map element. when we need it, we manually calculate where it need to go and 
  // fade it in and out. 

  // Note that I explicitly do not check for this zoom level on load becuase I only want it to show if the user zooms 
  // to it, not if they just come via a link to it becuase that is no fun. 

  map.on('zoomstart', function() {
    if (map.getZoom() == CWANT_LOGO_ZOOM_LEVEL ) {
      // We are leaving the logo zoom level, start fading out immediately
      // Direct DOM manipulation of the image allows CSS transition to work during zoom animation
      
      cwandtLogoSvgDiv.style.opacity = 0;
    }
  });
  
  map.on('zoomend', function() {  
    if (map.getZoom() == CWANT_LOGO_ZOOM_LEVEL ) {
      // We arrived at the logo zoom level, so position it below the disk and fade it in

      // Position it below the disk

      // We need to put the svg below the disk. The disk is a leaflet thing, not a DOM element so we have to use the map to get the position of the disk
      
      // Let's calculate the bounding box for our svg element 
      // // Position horizontally centered with disk, vertically 2 diameters below disk center

      const logoCenterLatLong = [ -2 * radiusMapUnits, 0];
      const logoWidthMapunits = radiusMapUnits * 2;     // Match the width of the disk

      const logoCenterPixels = map.latLngToContainerPoint(logoCenterLatLong);

      // Next lets find the width of the svg in pixels. We want it to be the same width as the disk.
      // note that we leave the height to be computed automatically to keep the aspect ratio. 

      logoLeftEdgeX = map.latLngToContainerPoint([0, -radiusMapUnits]).x;
      logoRightEdgeX = map.latLngToContainerPoint([0, radiusMapUnits]).x;

      logoWidthPixels = logoRightEdgeX - logoLeftEdgeX;
    
      cwandtLogoSvgDiv.style.left = logoCenterPixels.x + 'px';
      cwandtLogoSvgDiv.style.top = logoCenterPixels.y + 'px';

      cwandtLogoSvgDiv.style.width = logoWidthPixels + 'px';
      // Center both horizontally and vertically on the center point      
      cwandtLogoSvgDiv.style.transform = 'translate(-50%, -50%)'; 
      
      // Fade it in
      cwandtLogoSvgDiv.style.opacity = 1;

    }
  });

  // --- Countdown Timer for Banner
  // Calculate days remaining until campaign end (19 days from Oct 12, 2025)
  function updateDaysLeft() {
    const endDate = new Date('2025-10-31T23:59:59'); // 19 days from Oct 12, 2025
    const now = new Date();
    const msPerDay = 1000 * 60 * 60 * 24;
    const daysLeft = Math.floor((endDate - now) / msPerDay);
    
    const element = document.getElementById('days-left');
    if (element) {
      element.textContent = Math.max(0, daysLeft); // Don't show negative days
    }
  }
  
  // Update immediately and then daily
  updateDaysLeft();
  setInterval(updateDaysLeft, 1000 * 60 * 60); // Update every hour

  // --- Dynamic Banner Font Sizing
  // Adjust banner font size so text fills 75% of viewport width
  function resizeBanner() {
    const banner = document.getElementById('banner');
    if (!banner) return;
    
    const targetWidth = window.innerWidth * 0.60; // 60% of viewport width
    let fontSize = 10; // Start small
    banner.style.fontSize = fontSize + 'px';
    
    // Binary search for optimal font size
    let low = 10;
    let high = 200;
    let bestSize = 10;
    
    while (high - low > 1) {
      const mid = Math.floor((low + high) / 2);
      banner.style.fontSize = mid + 'px';
      
      const width = banner.offsetWidth;
      
      if (width < targetWidth) {
        low = mid;
        bestSize = mid;
      } else if (width > targetWidth) {
        high = mid;
      } else {
        bestSize = mid;
        break;
      }
    }
    
    banner.style.fontSize = bestSize + 'px';
  }
  
  // Size banner on load and window resize
  resizeBanner();
  window.addEventListener('resize', resizeBanner);

})();
