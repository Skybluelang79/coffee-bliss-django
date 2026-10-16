/* Coffee Bliss — 3D product visuals (Three.js)
   Renders every product card / detail visual from ONE shared WebGL renderer
   and blits each frame into small per-card 2D canvases. This keeps GPU
   context usage to a single WebGL context no matter how many cards a page has.

   Falls back gracefully to the server-rendered emoji when WebGL is missing,
   or when the visitor prefers reduced motion (a single static frame is drawn).
*/
(function () {
  "use strict";

  if (typeof THREE === "undefined") return;

  var canvases = Array.prototype.slice.call(
    document.querySelectorAll("canvas[data-p3d]")
  );
  if (!canvases.length) return;

  var REDUCED =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var compact = window.innerWidth < 768;
  var MAX_ITEMS = compact ? 10 : 24;

  /* ---- Shared renderer ------------------------------------------------- */
  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({
      antialias: !compact,
      alpha: true,
      preserveDrawingBuffer: true,
    });
  } catch (err) {
    return;
  }
  if (!renderer || !renderer.getContext()) return;

  renderer.setPixelRatio(1);
  renderer.setSize(512, 384, false);
  renderer.outputEncoding = THREE.sRGBEncoding;
  renderer.shadowMap.enabled = !compact;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(36, 4 / 3, 0.1, 100);
  camera.position.set(0, 1.5, 7.8);
  camera.lookAt(0, 0.15, 0);

  /* ---- Lighting -------------------------------------------------------- */
  scene.add(new THREE.HemisphereLight(0xfff3e2, 0x3a2416, 0.62));

  var key = new THREE.DirectionalLight(0xffe6bd, 1.3);
  key.position.set(4.5, 8, 5.5);
  key.castShadow = !compact;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.near = 1;
  key.shadow.camera.far = 30;
  key.shadow.camera.left = -6;
  key.shadow.camera.right = 6;
  key.shadow.camera.top = 8;
  key.shadow.camera.bottom = -6;
  key.shadow.radius = 4;
  scene.add(key);

  var rim = new THREE.PointLight(0xff9d54, 1.6, 40);
  rim.position.set(-6, 3, -5);
  scene.add(rim);

  var fill = new THREE.DirectionalLight(0xa9c8ff, 0.5);
  fill.position.set(-5, -2, 4);
  scene.add(fill);

  var floor = new THREE.Mesh(
    new THREE.PlaneGeometry(30, 30),
    new THREE.ShadowMaterial({ opacity: 0.3 })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -1.35;
  floor.receiveShadow = true;
  scene.add(floor);

  /* ---- Material helpers ------------------------------------------------ */
  function ceramic(hex, rough) {
    return new THREE.MeshStandardMaterial({
      color: hex,
      roughness: rough === undefined ? 0.34 : rough,
      metalness: 0.05,
    });
  }
  function gold() {
    return new THREE.MeshStandardMaterial({
      color: 0xc8963e,
      roughness: 0.25,
      metalness: 0.85,
    });
  }
  function shadowed(mesh) {
    mesh.castShadow = !compact;
    mesh.receiveShadow = !compact;
    return mesh;
  }

  /* ---- Model builders -------------------------------------------------- */
  var CUP_PROFILE = [
    [0.0, 0.0], [1.15, 0.0], [1.15, 0.18], [1.02, 0.35], [0.92, 1.7],
    [1.02, 2.0], [1.02, 2.08], [0.9, 2.08], [0.82, 1.75], [0.72, 0.55],
    [0.7, 0.35], [0.0, 0.35],
  ].map(function (p) {
    return new THREE.Vector2(p[0], p[1]);
  });

  function buildCup(o) {
    var g = new THREE.Group();
    var porcelain = ceramic(0xf6ecdb);

    var cup = shadowed(
      new THREE.Mesh(new THREE.LatheGeometry(CUP_PROFILE, 64), porcelain)
    );
    cup.position.y = -1.15;
    g.add(cup);

    var saucer = shadowed(
      new THREE.Mesh(new THREE.CylinderGeometry(1.38, 1.52, 0.12, 64), ceramic(0xe6d6bb, 0.42))
    );
    saucer.position.y = -1.27;
    g.add(saucer);

    var liquid = new THREE.Mesh(
      new THREE.CircleGeometry(0.78, 48),
      new THREE.MeshStandardMaterial({ color: o.liquid, roughness: 0.18, metalness: 0.12 })
    );
    liquid.rotation.x = -Math.PI / 2;
    liquid.position.y = 0.93;
    g.add(liquid);

    var crema = new THREE.Mesh(
      new THREE.RingGeometry(0.52, 0.78, 48),
      new THREE.MeshStandardMaterial({ color: 0xcaa06a, roughness: 0.5 })
    );
    crema.rotation.x = -Math.PI / 2;
    crema.position.y = 0.935;
    g.add(crema);

    var rimRing = new THREE.Mesh(new THREE.TorusGeometry(0.99, 0.03, 16, 64), gold());
    rimRing.rotation.x = Math.PI / 2;
    rimRing.position.y = 1.0;
    g.add(rimRing);

    var handle = shadowed(
      new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.13, 20, 48, Math.PI * 1.25), porcelain)
    );
    handle.position.set(1.0, 0.0, 0);
    handle.rotation.z = -Math.PI / 2.2;
    g.add(handle);

    return g;
  }

  function buildTeacup(o) {
    var g = buildCup(o);
    g.scale.set(1.08, 0.78, 1.08);
    return g;
  }

  function buildMug(o) {
    var g = new THREE.Group();
    var porcelain = ceramic(0xf3e6d2, 0.32);

    var body = shadowed(
      new THREE.Mesh(new THREE.CylinderGeometry(1.0, 0.92, 1.75, 64, 1, true), porcelain)
    );
    g.add(body);

    var base = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.92, 0.9, 0.12, 64), porcelain));
    base.position.y = -0.88;
    g.add(base);

    var inner = new THREE.Mesh(
      new THREE.CylinderGeometry(0.9, 0.9, 1.6, 64, 1, true),
      new THREE.MeshStandardMaterial({ color: 0xdfd0b8, roughness: 0.6, side: THREE.BackSide })
    );
    inner.position.y = 0.02;
    g.add(inner);

    var liquid = new THREE.Mesh(
      new THREE.CircleGeometry(0.88, 48),
      new THREE.MeshStandardMaterial({ color: o.liquid, roughness: 0.2, metalness: 0.1 })
    );
    liquid.rotation.x = -Math.PI / 2;
    liquid.position.y = 0.78;
    g.add(liquid);

    var band = new THREE.Mesh(new THREE.TorusGeometry(0.985, 0.055, 16, 64), gold());
    band.rotation.x = Math.PI / 2;
    band.position.y = -0.06;
    g.add(band);

    var lip = new THREE.Mesh(new THREE.TorusGeometry(0.99, 0.05, 16, 64), porcelain);
    lip.rotation.x = Math.PI / 2;
    lip.position.y = 0.86;
    g.add(lip);

    var handle = shadowed(
      new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.13, 20, 48, Math.PI * 1.5), porcelain)
    );
    handle.position.set(0.98, 0.0, 0);
    handle.rotation.z = Math.PI / 2;
    g.add(handle);

    return g;
  }

  function buildGlass(o) {
    var g = new THREE.Group();
    var glassMat = new THREE.MeshStandardMaterial({
      color: 0xe8f6ff,
      roughness: 0.05,
      metalness: 0.1,
      transparent: true,
      opacity: 0.24,
      side: THREE.DoubleSide,
    });

    var wall = new THREE.Mesh(
      new THREE.CylinderGeometry(0.74, 0.6, 2.3, 48, 1, true),
      glassMat
    );
    g.add(wall);

    var bottom = new THREE.Mesh(new THREE.CircleGeometry(0.6, 48), glassMat);
    bottom.rotation.x = -Math.PI / 2;
    bottom.position.y = -1.15;
    g.add(bottom);

    var coffee = shadowed(
      new THREE.Mesh(
        new THREE.CylinderGeometry(0.69, 0.57, 1.55, 48),
        new THREE.MeshStandardMaterial({ color: o.liquid, roughness: 0.15, metalness: 0.18 })
      )
    );
    coffee.position.y = -0.35;
    g.add(coffee);

    var foam = new THREE.Mesh(
      new THREE.CircleGeometry(0.69, 48),
      new THREE.MeshStandardMaterial({ color: 0xc3a172, roughness: 0.7 })
    );
    foam.rotation.x = -Math.PI / 2;
    foam.position.y = 0.44;
    g.add(foam);

    var iceMat = new THREE.MeshStandardMaterial({
      color: 0xdff2ff,
      roughness: 0.1,
      metalness: 0.05,
      transparent: true,
      opacity: 0.55,
    });
    var iceData = [
      [0.16, 0.18, -0.02, 0.6], [-0.2, -0.06, 0.12, -0.4], [0.02, -0.32, -0.18, 1.1],
    ];
    iceData.forEach(function (d) {
      var cube = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.34, 0.34), iceMat);
      cube.position.set(d[0], d[1], d[2]);
      cube.rotation.set(d[3], d[3] * 1.4, d[3] * 0.6);
      g.add(cube);
    });

    var straw = new THREE.Mesh(
      new THREE.CylinderGeometry(0.06, 0.06, 1.7, 16),
      new THREE.MeshStandardMaterial({ color: 0xd9a441, roughness: 0.35, metalness: 0.3 })
    );
    straw.position.set(0.28, 0.35, 0.1);
    straw.rotation.z = -0.16;
    g.add(straw);

    return g;
  }

  function buildBag(o) {
    var g = new THREE.Group();
    var paper = ceramic(o.roast, 0.72);

    var body = shadowed(new THREE.Mesh(new THREE.BoxGeometry(1.5, 2.05, 0.72), paper));
    g.add(body);

    var top = shadowed(new THREE.Mesh(new THREE.BoxGeometry(1.58, 0.18, 0.8), ceramic(o.roast, 0.62)));
    top.position.y = 1.05;
    g.add(top);

    var crease = new THREE.Mesh(
      new THREE.BoxGeometry(1.52, 0.04, 0.02),
      new THREE.MeshStandardMaterial({ color: 0x1d120a, roughness: 0.9 })
    );
    crease.position.set(0, 1.04, 0.4);
    g.add(crease);

    var label = new THREE.Mesh(
      new THREE.PlaneGeometry(1.12, 0.66),
      new THREE.MeshStandardMaterial({ color: 0xf6ecdb, roughness: 0.6 })
    );
    label.position.set(0, -0.22, 0.37);
    g.add(label);

    var mark = new THREE.Mesh(new THREE.CircleGeometry(0.19, 32), gold());
    mark.position.set(0, -0.22, 0.375);
    g.add(mark);

    var valve = new THREE.Mesh(
      new THREE.CircleGeometry(0.07, 24),
      new THREE.MeshStandardMaterial({ color: 0x4a3324, roughness: 0.8 })
    );
    valve.position.set(0.52, 0.78, 0.42);
    g.add(valve);

    return g;
  }

  function buildPlate(o) {
    var g = new THREE.Group();

    var plate = shadowed(
      new THREE.Mesh(new THREE.CylinderGeometry(1.55, 1.35, 0.12, 64), ceramic(0xf6ecdb, 0.3))
    );
    plate.position.y = -0.95;
    g.add(plate);

    var inner = new THREE.Mesh(
      new THREE.CylinderGeometry(1.2, 1.24, 0.04, 64),
      ceramic(0xe6d6bb, 0.4)
    );
    inner.position.y = -0.88;
    g.add(inner);

    var pastry = shadowed(
      new THREE.Mesh(
        new THREE.TorusGeometry(0.66, 0.29, 18, 40, Math.PI * 1.15),
        new THREE.MeshStandardMaterial({ color: 0xc4813c, roughness: 0.78 })
      )
    );
    pastry.rotation.x = Math.PI / 2;
    pastry.rotation.z = Math.PI * 0.42;
    pastry.position.set(-0.08, -0.6, 0.05);
    g.add(pastry);

    var crumb = new THREE.Mesh(
      new THREE.SphereGeometry(0.14, 16, 12),
      new THREE.MeshStandardMaterial({ color: 0xa8692d, roughness: 0.85 })
    );
    crumb.position.set(0.62, -0.72, 0.35);
    g.add(crumb);

    g.scale.setScalar(0.9);
    return g;
  }

  var BUILDERS = {
    cup: buildCup,
    teacup: buildTeacup,
    mug: buildMug,
    glass: buildGlass,
    bag: buildBag,
    plate: buildPlate,
  };

  /* ---- Build render items --------------------------------------------- */
  var items = [];
  var i, canvas;

  for (i = 0; i < canvases.length && items.length < MAX_ITEMS; i++) {
    canvas = canvases[i];
    var type = canvas.dataset.p3d || "cup";
    var ctx = canvas.getContext("2d");
    if (!ctx || !BUILDERS[type]) continue;

    var group = BUILDERS[type]({
      liquid: canvas.dataset.p3dLiquid || "#4a2b18",
      roast: canvas.dataset.p3dRoast || "#9a6b3f",
    });
    if (!group) continue;

    items.push({
      canvas: canvas,
      ctx: ctx,
      group: group,
      parent: canvas.parentElement,
      cw: canvas.width || 512,
      ch: canvas.height || 384,
      phase: Math.random() * Math.PI * 2,
      baseY: 0,
      visible: false,
      drawn: false,
    });
  }

  if (!items.length) return;

  /* ---- Visibility (only animate what is on screen) --------------------- */
  var observer = null;
  if ("IntersectionObserver" in window) {
    observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          var item = entry.target.__p3d;
          if (item) item.visible = entry.isIntersecting;
        });
      },
      { rootMargin: "120px 0px" }
    );
    items.forEach(function (item) {
      item.canvas.__p3d = item;
      observer.observe(item.canvas);
    });
  } else {
    items.forEach(function (item) {
      item.visible = true;
    });
  }

  /* ---- Render one item into its own canvas ----------------------------- */
  camera.aspect = 4 / 3;
  camera.updateProjectionMatrix();
  var lastAspect = 4 / 3;

  function drawItem(item, t) {
    var aspect = item.cw / item.ch;
    if (aspect !== lastAspect) {
      camera.aspect = aspect;
      camera.updateProjectionMatrix();
      lastAspect = aspect;
    }

    var sway = Math.sin(t * 0.6 + item.phase) * 0.5;
    item.group.rotation.y = sway;
    item.group.rotation.z = Math.sin(t * 0.4 + item.phase) * 0.02;
    item.group.position.y = item.baseY + Math.sin(t * 1.1 + item.phase) * 0.07;

    scene.add(item.group);
    renderer.render(scene, camera);
    scene.remove(item.group);

    item.ctx.clearRect(0, 0, item.cw, item.ch);
    item.ctx.drawImage(renderer.domElement, 0, 0, item.cw, item.ch);

    if (!item.drawn) {
      item.drawn = true;
      if (item.parent) item.parent.classList.add("media-3d-ready");
      item.canvas.classList.add("is-live");
    }
  }

  /* ---- Animate --------------------------------------------------------- */
  function renderAll(t) {
    for (var n = 0; n < items.length; n++) {
      if (items[n].visible || !items[n].drawn) drawItem(items[n], t);
    }
  }

  if (REDUCED) {
    renderAll(0);
    return;
  }

  var clock = new THREE.Clock();
  var running = true;
  var FRAME = 1 / 30;
  var acc = 0;

  function animate() {
    if (!running) return;
    requestAnimationFrame(animate);
    var dt = clock.getDelta();
    acc += dt;
    if (acc < FRAME) return;
    acc = 0;
    renderAll(clock.getElapsedTime());
  }
  animate();

  document.addEventListener("visibilitychange", function () {
    running = !document.hidden;
    if (running) {
      clock.start();
      animate();
    }
  });
})();
