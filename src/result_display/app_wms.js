const offlineLayer = new ol.layer.Tile({
    source: new ol.source.XYZ({
        tileUrlFunction: function() {
            return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAEBgIApD5fRAAAAABJRU5ErkJggg==';
        }
    }),
    visible: false
});

const osmLayer = new ol.layer.Tile({
    source: new ol.source.OSM(),
    visible: false
});

const satelliteLayer = new ol.layer.Tile({
    source: new ol.source.XYZ({
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
    }),
    visible: true
});

let wmsLayer = null;

const map = new ol.Map({
    target: 'map',
    layers: [offlineLayer, osmLayer, satelliteLayer],
    view: new ol.View({
        center: ol.proj.fromLonLat([118.78, 44.84]),
        zoom: 10
    }),
    controls: ol.control.defaults.defaults({
        zoom: false
    })
});

document.getElementById('map').style.backgroundColor = '#e8ebe8';

let currentTimeScale = 'yearly';
let currentDataType = 'syld';
let currentFrameIndex = 0;
let isPlaying = false;
let playbackInterval = null;
let playbackSpeed = 1000;
let timeFrames = [];
let currentScaleInfo = null;
let initialCenter = null;
let initialZoom = null;

const variableLabels = {
    syld: 'Sediment yield (SYLD)',
    surq_gen: 'Surface runoff (SURQ_GEN)'
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

function buildWMSUrl(dataType, timeScale, simTime) {
    const config = GEOSERVER_CONFIG[dataType];
    const scaleInfo = config.scales_info.find(s => s.scale === timeScale);

    if (!scaleInfo) return null;

    const urlInfo = config.url_info;
    const params = new URLSearchParams({
        service: urlInfo.service,
        version: urlInfo.version,
        request: urlInfo.request,
        layers: scaleInfo.layers,
        styles: scaleInfo.styles,
        srs: urlInfo.srs,
        bbox: urlInfo.bbox,
        width: urlInfo.width,
        height: urlInfo.height,
        format: urlInfo.format,
        transparent: urlInfo.transparent,
        bgcolor: urlInfo.bgcolor,
        viewparams: `sim_time:${simTime};scale:${timeScale}`
    });

    return `${urlInfo.base_url}?${params.toString()}`;
}

function generateTimeFrames(startDate, endDate, scale) {
    const frames = [];
    const start = new Date(startDate);
    const end = new Date(endDate);

    if (scale === 'yearly') {
        for (let year = start.getFullYear(); year <= end.getFullYear(); year++) {
            frames.push(`${year}-01-01`);
        }
    } else if (scale === 'monthly') {
        const current = new Date(start);
        while (current <= end) {
            const month = String(current.getMonth() + 1).padStart(2, '0');
            frames.push(`${current.getFullYear()}-${month}-01`);
            current.setMonth(current.getMonth() + 1);
        }
    }

    return frames;
}

function initWMSLayer() {
    const config = GEOSERVER_CONFIG[currentDataType];
    if (!config) return false;

    currentScaleInfo = config.scales_info.find(s => s.scale === currentTimeScale);
    if (!currentScaleInfo) return false;

    timeFrames = generateTimeFrames(currentScaleInfo.time[0], currentScaleInfo.time[1], currentTimeScale);

    if (wmsLayer) {
        map.removeLayer(wmsLayer);
    }

    const urlInfo = config.url_info;
    wmsLayer = new ol.layer.Image({
        source: new ol.source.ImageWMS({
            url: urlInfo.base_url,
            params: {
                'LAYERS': currentScaleInfo.layers,
                'STYLES': currentScaleInfo.styles,
                'SRS': urlInfo.srs,
                'FORMAT': urlInfo.format,
                'TRANSPARENT': urlInfo.transparent,
                'BGCOLOR': urlInfo.bgcolor,
                'viewparams': `sim_time:${timeFrames[0]};scale:${currentTimeScale}`
            },
            serverType: 'geoserver'
        })
    });

    map.addLayer(wmsLayer);

    const bbox = urlInfo.bbox.split(',').map(parseFloat);
    const extent = ol.proj.transformExtent(bbox, 'EPSG:4326', 'EPSG:3857');
    map.getView().fit(extent, {
        padding: [80, 80, 200, 80],
        duration: 1000
    });

    initialCenter = map.getView().getCenter();
    initialZoom = map.getView().getZoom();
    window.initialExtent = extent;

    if (timeFrames.length > 0) {
        document.getElementById('startDate').textContent = timeFrames[0];
        document.getElementById('endDate').textContent = timeFrames[timeFrames.length - 1];
        document.getElementById('timelineSlider').max = timeFrames.length - 1;

        updateDataForFrame(0);
        updateLegend();
    }

    return true;
}

function updateDataForFrame(frameIndex) {
    if (frameIndex < 0 || frameIndex >= timeFrames.length) return;

    currentFrameIndex = frameIndex;
    const simTime = timeFrames[frameIndex];

    if (wmsLayer) {
        const source = wmsLayer.getSource();
        const params = source.getParams();
        params.viewparams = `sim_time:${simTime};scale:${currentTimeScale}`;
        source.updateParams(params);
    }

    document.getElementById('currentDate').textContent = simTime;
    document.getElementById('timelineSlider').value = frameIndex;
}

function updateLegend() {
    const legendTitle = document.getElementById('legendTitle');
    const legendItems = document.getElementById('legendItems');

    legendTitle.textContent = variableLabels[currentDataType] || currentDataType.toUpperCase();
    if (!currentScaleInfo) return;

    const levels = currentScaleInfo.levels;
    const colors = colorScales[currentDataType] || colorScales.syld;
    const existingItems = legendItems.querySelectorAll('.legend-item');

    for (let i = 0; i < levels.length; i++) {
        const levelMax = levels[levels.length - 1 - i];
        const levelMin = i < levels.length - 1 ? levels[levels.length - 2 - i] : 0;
        const levelText = `${levelMin.toFixed(3)} - ${levelMax.toFixed(3)}`;

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
        colorBox.style.backgroundColor = colors[i] || colors[colors.length - 1];
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

async function onTimeScaleChange(event) {
    const newTimeScale = event.target.value;
    if (newTimeScale !== currentTimeScale) {
        const wasPlaying = isPlaying;
        currentTimeScale = newTimeScale;
        pauseTimeline();
        currentFrameIndex = 0;
        initWMSLayer();
        if (wasPlaying) {
            playTimeline();
        }
    }
}

function onDataTypeChange(event) {
    const newDataType = event.target.value;
    if (newDataType !== currentDataType) {
        const wasPlaying = isPlaying;
        currentDataType = newDataType;
        pauseTimeline();
        currentFrameIndex = 0;
        initWMSLayer();
        if (wasPlaying) {
            playTimeline();
        }
    }
}

function resetMapView() {
    if (window.initialExtent) {
        map.getView().fit(window.initialExtent, {
            padding: [80, 80, 200, 80],
            duration: 500
        });
    } else if (initialCenter && initialZoom) {
        map.getView().animate({
            center: initialCenter,
            zoom: initialZoom,
            duration: 500
        });
    }
}

function zoomIn() {
    const view = map.getView();
    view.animate({
        zoom: view.getZoom() + 1,
        duration: 250
    });
}

function zoomOut() {
    const view = map.getView();
    view.animate({
        zoom: view.getZoom() - 1,
        duration: 250
    });
}

function toggleBaseLayer() {
    const osmVisible = osmLayer.getVisible();
    osmLayer.setVisible(!osmVisible);
    satelliteLayer.setVisible(osmVisible);
}

(function init() {
    initWMSLayer();

    document.getElementById('playPause').addEventListener('click', togglePlayPause);
    document.getElementById('prevFrame').addEventListener('click', previousFrame);
    document.getElementById('nextFrame').addEventListener('click', nextFrame);
    document.getElementById('timelineSlider').addEventListener('input', onSliderChange);
    document.getElementById('timeScale').addEventListener('change', onTimeScaleChange);
    document.getElementById('dataType').addEventListener('change', onDataTypeChange);
    document.getElementById('resetView').addEventListener('click', resetMapView);
    document.getElementById('zoomIn').addEventListener('click', zoomIn);
    document.getElementById('zoomOut').addEventListener('click', zoomOut);
    document.getElementById('toggleLayer').addEventListener('click', toggleBaseLayer);
})();
