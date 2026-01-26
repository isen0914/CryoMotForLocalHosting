/* ------------ INSERTED FROM viewer_vtkjs.html (COMPATIBLE VERSION) -------------- */
/*   This is a simplified & container-safe version of your viewer_vtkjs.html script */
/* ------------------------------------------------------------------------------- */
// VTK.js imports
function getQueryParam(name) {
    const params = new URLSearchParams(window.location.search);
    return params.get(name);
}



function parseNpy(buffer) {
    const dv = new DataView(buffer);
    const magic = String.fromCharCode.apply(null, new Uint8Array(buffer,0,6));
    if (magic !== "\\x93NUMPY") throw new Error("Not a .npy file");

    let offset = 6;
    const major = dv.getUint8(offset++); 
    const minor = dv.getUint8(offset++);
    let headerLen = major===1 ? dv.getUint16(offset,true) : dv.getUint32(offset,true);
    offset += major===1 ? 2 : 4;

    const headerBytes = new Uint8Array(buffer, offset, headerLen);
    const header = new TextDecoder("utf8").decode(headerBytes);
    offset += headerLen;

    const descr = header.match(/'descr':\\s*'([^']+)'/)[1];
    const shape = header.match(/'shape':\\s*\\(([^)]*)\\)/)[1]
                .split(',')
                .map(x => parseInt(x.trim()))
                .filter(x => !isNaN(x));
    const count = shape.reduce((a,b)=>a*b);

    let typed;
    const t = descr.slice(-2);
    if (t==="f4") typed = new Float32Array(buffer, offset, count);
    else if (t==="u1") typed = new Uint8Array(buffer, offset, count);
    else throw new Error("Unsupported dtype: "+descr);

    return {shape, data: typed, descr};
}

function vtkImageFromNpy(parsed) {
    const shp = parsed.shape;
    let z=1, y, x, c=1;

    if (shp.length === 3) [z,y,x] = shp;
    else if (shp.length === 2) [y,x] = shp;
    else throw new Error("Shape must be 2D or 3D");

    const imageData = vtk.Common.DataModel.vtkImageData.newInstance();
    imageData.setDimensions(x, y, z);

    const vtkArr = vtk.Common.Core.vtkDataArray.newInstance({
        numberOfComponents: c,
        values: parsed.data
    });
    vtkArr.setName("Scalars");
    imageData.getPointData().setScalars(vtkArr);

    return imageData;
}

function renderVTK(imageData) {
    // attach to container
    const root = document.getElementById("vtkContainer");

    const full = vtk.Rendering.Misc.vtkFullScreenRenderWindow.newInstance({
        rootContainer: root,
        containerStyle: { width: "100%", height: "100%" },
        background: [0.1,0.1,0.1]
    });

    const renderer = full.getRenderer();
    const renWin = full.getRenderWindow();

    const mapper = vtk.Rendering.Core.vtkVolumeMapper.newInstance();
    mapper.setSampleDistance(parseFloat(sampleDist.value)||1);
    mapper.setInputData(imageData);

    const actor = vtk.Rendering.Core.vtkVolume.newInstance();
    actor.setMapper(mapper);

    const ctfun = vtk.Rendering.Core.vtkColorTransferFunction.newInstance();
    const ofun = vtk.Common.DataModel.vtkPiecewiseFunction.newInstance();

    const [min, max] = imageData.getPointData().getScalars().getRange();
    ctfun.addRGBPoint(min, 0,0,0);
    ctfun.addRGBPoint(max, 1,1,1);

    ofun.addPoint(min, 0.0);
    ofun.addPoint(max, 1.0);

    actor.getProperty().setRGBTransferFunction(0, ctfun);
    actor.getProperty().setScalarOpacity(0, ofun);
    actor.getProperty().setInterpolationTypeToLinear();

    renderer.addVolume(actor);
    renderer.resetCamera();
    renWin.render();

    sampleDist.oninput = () => {
        mapper.setSampleDistance(parseFloat(sampleDist.value));
        renWin.render();
    };
}

document.getElementById("fileInput").addEventListener("change", (ev)=>{
    const file = ev.target.files[0];
    const reader = new FileReader();
    reader.onload = e => {
        const parsed = parseNpy(e.target.result);
        renderVTK(vtkImageFromNpy(parsed));
    };
    reader.readAsArrayBuffer(file);
});

document.getElementById("loadUrl").addEventListener("click", async ()=>{
    const url = document.getElementById("urlInput").value;
    const resp = await fetch(url);
    const buf = await resp.arrayBuffer();
    const parsed = parseNpy(buf);
    renderVTK(vtkImageFromNpy(parsed));
});