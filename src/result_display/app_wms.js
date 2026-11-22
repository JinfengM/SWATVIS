function createBaseLayers() {
    return {
        osm: new ol.layer.Tile({
            source: new ol.source.OSM(),
            visible: false
        }),
        satellite: new ol.layer.Tile({
            source: new ol.source.XYZ({
                url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
            }),
            visible: false
        })
    };
}

const primaryBaseLayers = createBaseLayers();
const comparisonBaseLayers = createBaseLayers();
const primaryView = new ol.View({
    center: ol.proj.fromLonLat([118.78, 44.84]),
    zoom: 10
});
const comparisonView = new ol.View({
    center: ol.proj.fromLonLat([118.78, 44.84]),
    zoom: 10
});

const map = new ol.Map({
    target: 'map',
    layers: Object.values(primaryBaseLayers),
    view: primaryView,
    controls: ol.control.defaults.defaults({
        zoom: false
    })
});

const comparisonMap = new ol.Map({
    target: 'comparisonMap',
    layers: Object.values(comparisonBaseLayers),
    view: comparisonView,
    controls: ol.control.defaults.defaults({
        zoom: false
    })
});

let synchronizingViews = false;

function synchronizeViewProperty(updateTarget) {
    if (synchronizingViews) return;
    synchronizingViews = true;
    updateTarget();
    synchronizingViews = false;
}

function synchronizeViews(sourceView, targetView, shouldSynchronize = () => true) {
    sourceView.on('change:center', () => {
        if (!shouldSynchronize()) return;
        synchronizeViewProperty(() => targetView.setCenter(sourceView.getCenter()));
    });
    sourceView.on('change:resolution', () => {
        if (!shouldSynchronize()) return;
        synchronizeViewProperty(() => targetView.setResolution(sourceView.getResolution()));
    });
    sourceView.on('change:rotation', () => {
        if (!shouldSynchronize()) return;
        synchronizeViewProperty(() => targetView.setRotation(sourceView.getRotation()));
    });
}

synchronizeViews(primaryView, comparisonView);
synchronizeViews(comparisonView, primaryView, () => comparisonMode);

let wmsLayer = null;
let comparisonWmsLayer = null;
let currentTimeScale = 'yearly';
let currentDataType = 'syld';
let currentFrameIndex = 0;
let comparisonFrameIndex = null;
let comparisonMode = false;
let isPlaying = false;
let playbackInterval = null;
const playbackSpeed = 1000;
let timeFrames = [];
let currentScaleInfo = null;
let initialCenter = null;
let initialZoom = null;

const variableLabels = {
    syld: 'SYLD (t/ha)',
    surq_gen: 'SURQ_GEN (mm)'
};

const colorScales = {
    syld: [
        'rgb(103, 0, 31)', 'rgb(178, 24, 43)', 'rgb(214, 96, 77)',
        'rgb(244, 165, 130)', 'rgb(253, 219, 199)', 'rgb(209, 229, 240)',
        'rgb(146, 197, 222)', 'rgb(67, 147, 195)', 'rgb(33, 102, 172)', 'rgb(5, 48, 97)'
    ],
    surq_gen: [
        'rgb(103, 0, 31)', 'rgb(178, 24, 43)', 'rgb(214, 96, 77)',
        'rgb(244, 165, 130)', 'rgb(253, 219, 199)', 'rgb(209, 229, 240)',
        'rgb(146, 197, 222)', 'rgb(67, 147, 195)', 'rgb(33, 102, 172)', 'rgb(5, 48, 97)'
    ]
};

function generateTimeFrames(startDate, endDate, scale) {
    const frames = [];
    const start = new Date(startDate);
    const end = new Date(endDate);

    if (scale === 'yearly') {
        for (let year = start.getUTCFullYear(); year <= end.getUTCFullYear(); year++) {
            frames.push(`${year}-01-01`);
        }
    } else if (scale === 'monthly') {
        const current = new Date(start);
        while (current <= end) {
            const month = String(current.getUTCMonth() + 1).padStart(2, '0');
            frames.push(`${current.getUTCFullYear()}-${month}-01`);
            current.setUTCMonth(current.getUTCMonth() + 1);
        }
    }

    return frames;
}

function createWMSLayer(frameIndex) {
    const config = GEOSERVER_CONFIG[currentDataType];
    const urlInfo = config.url_info;
    const simTime = timeFrames[frameIndex];

    return new ol.layer.Image({
        source: new ol.source.ImageWMS({
            url: urlInfo.base_url,
            params: {
                'LAYERS': currentScaleInfo.layers,
                'STYLES': currentScaleInfo.styles,
                'SRS': urlInfo.srs,
                'FORMAT': urlInfo.format,
                'TRANSPARENT': urlInfo.transparent,
                'BGCOLOR': urlInfo.bgcolor,
                'viewparams': `sim_time:${simTime};scale:${currentTimeScale}`
            },
            serverType: 'geoserver'
        })
    });
}

function defaultComparisonFrame() {
    if (timeFrames.length < 2) return 0;
    return currentFrameIndex === timeFrames.length - 1 ? 0 : timeFrames.length - 1;
}

function removeWMSLayers() {
    if (wmsLayer) {
        map.removeLayer(wmsLayer);
        wmsLayer = null;
    }
    if (comparisonWmsLayer) {
        comparisonMap.removeLayer(comparisonWmsLayer);
        comparisonWmsLayer = null;
    }
}

function initWMSLayer() {
    const config = GEOSERVER_CONFIG[currentDataType];
    if (!config) return false;

    currentScaleInfo = config.scales_info.find(scale => scale.scale === currentTimeScale);
    if (!currentScaleInfo) return false;

    timeFrames = generateTimeFrames(
        currentScaleInfo.time[0],
        currentScaleInfo.time[1],
        currentTimeScale
    );
    if (timeFrames.length === 0) return false;

    currentFrameIndex = Math.min(currentFrameIndex, timeFrames.length - 1);
    if (comparisonFrameIndex === null || comparisonFrameIndex >= timeFrames.length) {
        comparisonFrameIndex = defaultComparisonFrame();
    }

    removeWMSLayers();
    wmsLayer = createWMSLayer(currentFrameIndex);
    map.addLayer(wmsLayer);

    if (comparisonMode) {
        comparisonWmsLayer = createWMSLayer(comparisonFrameIndex);
        comparisonMap.addLayer(comparisonWmsLayer);
    }

    const urlInfo = config.url_info;
    const bbox = urlInfo.bbox.split(',').map(parseFloat);
    const extent = ol.proj.transformExtent(bbox, 'EPSG:4326', 'EPSG:3857');
    primaryView.fit(extent, {
        size: map.getSize(),
        padding: comparisonMode ? [50, 15, 160, 35] : [20, 20, 200, 150],
        duration: 1000
    });

    initialCenter = primaryView.getCenter();
    initialZoom = primaryView.getZoom();
    window.initialExtent = extent;

    const timelineSlider = document.getElementById('timelineSlider');
    const comparisonSlider = document.getElementById('comparisonTimelineSlider');
    document.getElementById('startDate').textContent = timeFrames[0];
    document.getElementById('endDate').textContent = timeFrames[timeFrames.length - 1];
    timelineSlider.max = timeFrames.length - 1;
    comparisonSlider.max = timeFrames.length - 1;

    updateDataForFrame(currentFrameIndex);
    updateComparisonDataForFrame(comparisonFrameIndex);
    updateLegend();
    return true;
}

function updateLayerTime(layer, simTime) {
    if (!layer) return;
    layer.getSource().updateParams({
        viewparams: `sim_time:${simTime};scale:${currentTimeScale}`
    });
}

function updateDataForFrame(frameIndex) {
    if (frameIndex < 0 || frameIndex >= timeFrames.length) return;

    currentFrameIndex = frameIndex;
    const simTime = timeFrames[frameIndex];
    updateLayerTime(wmsLayer, simTime);

    document.getElementById('currentDate').textContent = simTime;
    document.getElementById('primaryMapDate').textContent = `Left: ${simTime}`;
    document.getElementById('timelineSlider').value = frameIndex;
}

function updateComparisonDataForFrame(frameIndex) {
    if (frameIndex < 0 || frameIndex >= timeFrames.length) return;

    comparisonFrameIndex = frameIndex;
    const simTime = timeFrames[frameIndex];
    updateLayerTime(comparisonWmsLayer, simTime);

    document.getElementById('comparisonDate').textContent = simTime;
    document.getElementById('comparisonMapDate').textContent = `Right: ${simTime}`;
    document.getElementById('comparisonTimelineSlider').value = frameIndex;
}

function formatLegendValue(value) {
    if (!Number.isFinite(value)) return String(value);
    if (value === 0) return '0';

    const absoluteValue = Math.abs(value);
    if (absoluteValue < 0.001 || absoluteValue >= 10000) {
        return Number(value.toPrecision(4)).toExponential();
    }
    return Number(value.toPrecision(6)).toString();
}

function updateLegend() {
    const legendTitle = document.getElementById('legendTitle');
    const legendItems = document.getElementById('legendItems');

    legendTitle.textContent = variableLabels[currentDataType] || currentDataType.toUpperCase();
    if (!currentScaleInfo) return;

    const levels = currentScaleInfo.levels;
    const colors = currentScaleInfo.colors || [...(colorScales[currentDataType] || colorScales.syld)].reverse();
    const existingItems = legendItems.querySelectorAll('.legend-item');

    for (let i = 0; i < levels.length; i++) {
        const levelIndex = levels.length - 1 - i;
        const levelMax = levels[levelIndex];
        const levelText = levelIndex === 0
            ? (levelMax === 0 ? "0" : `≤ ${formatLegendValue(levelMax)}`)
            : `${formatLegendValue(levels[levelIndex - 1])} – ${formatLegendValue(levelMax)}`;

        let item = existingItems[i];
        if (!item) {
            item = document.createElement('div');
            item.className = 'legend-item';
            item.innerHTML = `
                <div class="legend-color"></div>
                <div class="legend-value"></div>
            `;
            legendItems.appendChild(item);
        }

        const colorBox = item.querySelector('.legend-color');
        const valueText = item.querySelector('.legend-value');
        colorBox.style.backgroundColor = colors[levelIndex] || colors[colors.length - 1];
        valueText.textContent = levelText;
    }

    for (let i = existingItems.length - 1; i >= levels.length; i--) {
        legendItems.removeChild(existingItems[i]);
    }
}

function playTimeline() {
    if (isPlaying) return;

    if (currentFrameIndex >= timeFrames.length - 1) {
        updateDataForFrame(0);
    }

    isPlaying = true;
    document.getElementById('playPause').textContent = '||';

    playbackInterval = setInterval(() => {
        if (currentFrameIndex < timeFrames.length - 1) {
            updateDataForFrame(currentFrameIndex + 1);
        } else {
            pauseTimeline();
        }
    }, playbackSpeed);
}

function pauseTimeline() {
    isPlaying = false;
    document.getElementById('playPause').textContent = '>';

    if (playbackInterval) {
        clearInterval(playbackInterval);
        playbackInterval = null;
    }
}

function togglePlayPause() {
    if (isPlaying) {
        pauseTimeline();
    } else {
        playTimeline();
    }
}

function previousFrame() {
    pauseTimeline();
    if (currentFrameIndex > 0) {
        updateDataForFrame(currentFrameIndex - 1);
    }
}

function nextFrame() {
    pauseTimeline();
    if (currentFrameIndex < timeFrames.length - 1) {
        updateDataForFrame(currentFrameIndex + 1);
    }
}

function onSliderChange(event) {
    pauseTimeline();
    updateDataForFrame(parseInt(event.target.value, 10));
}

function onComparisonSliderChange(event) {
    updateComparisonDataForFrame(parseInt(event.target.value, 10));
}

function onTimeScaleChange(event) {
    const newTimeScale = event.target.value;
    if (newTimeScale === currentTimeScale) return;

    const wasPlaying = isPlaying;
    currentTimeScale = newTimeScale;
    pauseTimeline();
    currentFrameIndex = 0;
    comparisonFrameIndex = null;
    initWMSLayer();
    if (wasPlaying) playTimeline();
}

function onDataTypeChange(event) {
    const newDataType = event.target.value;
    if (newDataType === currentDataType) return;

    const wasPlaying = isPlaying;
    currentDataType = newDataType;
    pauseTimeline();
    currentFrameIndex = 0;
    comparisonFrameIndex = null;
    initWMSLayer();
    if (wasPlaying) playTimeline();
}

function resetMapView() {
    if (window.initialExtent) {
        primaryView.fit(window.initialExtent, {
            size: map.getSize(),
            padding: comparisonMode ? [50, 15, 160, 35] : [20, 20, 200, 150],
            duration: 500
        });
    } else if (initialCenter && initialZoom !== null) {
        primaryView.animate({
            center: initialCenter,
            zoom: initialZoom,
            duration: 500
        });
    }
}

function zoomIn() {
    primaryView.animate({
        zoom: primaryView.getZoom() + 1,
        duration: 250
    });
}

function zoomOut() {
    primaryView.animate({
        zoom: primaryView.getZoom() - 1,
        duration: 250
    });
}

function toggleBaseLayer() {
    const osm = primaryBaseLayers.osm.getVisible();
    const satellite = primaryBaseLayers.satellite.getVisible();
    [primaryBaseLayers, comparisonBaseLayers].forEach(baseLayers => {
        baseLayers.osm.setVisible(!osm && !satellite);
        baseLayers.satellite.setVisible(osm);
    });
}

function toggleComparisonMode() {
    pauseTimeline();
    comparisonMode = !comparisonMode;

    const toggleButton = document.getElementById('toggleComparison');
    document.body.classList.toggle('comparison-mode', comparisonMode);
    toggleButton.classList.toggle('active', comparisonMode);
    toggleButton.setAttribute('aria-pressed', String(comparisonMode));

    if (comparisonMode) {
        if (comparisonFrameIndex === null || comparisonFrameIndex === currentFrameIndex) {
            comparisonFrameIndex = defaultComparisonFrame();
        }
        comparisonWmsLayer = createWMSLayer(comparisonFrameIndex);
        comparisonMap.addLayer(comparisonWmsLayer);
        updateComparisonDataForFrame(comparisonFrameIndex);
    } else if (comparisonWmsLayer) {
        comparisonMap.removeLayer(comparisonWmsLayer);
        comparisonWmsLayer = null;
    }

    requestAnimationFrame(() => {
        map.updateSize();
        comparisonMap.updateSize();
    });
}

(function init() {
    initWMSLayer();

    document.getElementById('playPause').addEventListener('click', togglePlayPause);
    document.getElementById('prevFrame').addEventListener('click', previousFrame);
    document.getElementById('nextFrame').addEventListener('click', nextFrame);
    document.getElementById('timelineSlider').addEventListener('input', onSliderChange);
    document.getElementById('comparisonTimelineSlider').addEventListener('input', onComparisonSliderChange);
    document.getElementById('timeScale').addEventListener('change', onTimeScaleChange);
    document.getElementById('dataType').addEventListener('change', onDataTypeChange);
    document.getElementById('resetView').addEventListener('click', resetMapView);
    document.getElementById('zoomIn').addEventListener('click', zoomIn);
    document.getElementById('zoomOut').addEventListener('click', zoomOut);
    document.getElementById('toggleLayer').addEventListener('click', toggleBaseLayer);
    document.getElementById('toggleComparison').addEventListener('click', toggleComparisonMode);
})();
