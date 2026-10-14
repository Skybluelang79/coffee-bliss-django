/* Coffee Bliss — 3D hero scene (Three.js)
   A slowly rotating coffee cup, steam, and floating beans.
   Falls back gracefully when WebGL is unavailable. */
(function () {
  "use strict";

  const canvas = document.getElementById("hero-canvas");
  if (!canvas || typeof THREE === "undefined") return;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  } catch (e) {
    return;
  }

  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, canvas.clientWidth / canvas.clientHeight, 0.1, 100);
  camera.position.set(0, 1.6, 8);

  const group = new THREE.Group();
  scene.add(group);

  // ---- Lighting ---------------------------------------------------------
  scene.add(new THREE.AmbientLight(0xffe9cf, 0.55));

  const key = new THREE.DirectionalLight(0xffd9a0, 1.6);
  key.position.set(5, 8, 6);
  scene.add(key);

  const rim = new THREE.PointLight(0xd2691e, 2.2, 30);
  rim.position.set(-6, 2, -4);
  scene.add(rim);

  const fill = new THREE.PointLight(0x5b9bd5, 0.8, 30);
  fill.position.set(6, -2, 4);
  scene.add(fill);

  // ---- Materials --------------------------------------------------------
  const ceramic = new THREE.MeshStandardMaterial({
    color: 0xf3e7d3,
    roughness: 0.35,
    metalness: 0.05,
  });
  const ceramicDark = new THREE.MeshStandardMaterial({
    color: 0xe4d3b8,
    roughness: 0.4,
    metalness: 0.05,
  });
  const coffeeMat = new THREE.MeshStandardMaterial({
    color: 0x3b1f12,
    roughness: 0.25,
    metalness: 0.15,
  });
  const goldMat = new THREE.MeshStandardMaterial({
    color: 0xc8963e,
    roughness: 0.25,
    metalness: 0.85,
  });

  // ---- Coffee cup (lathe profile) --------------------------------------
  const profile = [];
  profile.push(new THREE.Vector2(0.0, 0.0));
  profile.push(new THREE.Vector2(1.15, 0.0));
  profile.push(new THREE.Vector2(1.15, 0.18));
  profile.push(new THREE.Vector2(1.02, 0.35));
  profile.push(new THREE.Vector2(0.92, 1.7));
  profile.push(new THREE.Vector2(1.02, 2.0));
  profile.push(new THREE.Vector2(1.02, 2.08));
  profile.push(new THREE.Vector2(0.9, 2.08));
  profile.push(new THREE.Vector2(0.82, 1.75));
  profile.push(new THREE.Vector2(0.72, 0.55));
  profile.push(new THREE.Vector2(0.7, 0.35));
  profile.push(new THREE.Vector2(0.0, 0.35));
  const cup = new THREE.Mesh(new THREE.LatheGeometry(profile, 64), ceramic);
  cup.position.y = -1.1;
  group.add(cup);

  // Saucer
  const saucer = new THREE.Mesh(new THREE.CylinderGeometry(1.35, 1.5, 0.12, 64), ceramicDark);
  saucer.position.y = -1.22;
  group.add(saucer);

  // Coffee surface
  const coffeeGeo = new THREE.CircleGeometry(0.78, 48);
  const coffee = new THREE.Mesh(coffeeGeo, coffeeMat);
  coffee.rotation.x = -Math.PI / 2;
  coffee.position.y = 0.95;
  group.add(coffee);

  // Gold rim ring
  const rimRing = new THREE.Mesh(new THREE.TorusGeometry(0.98, 0.035, 16, 64), goldMat);
  rimRing.rotation.x = Math.PI / 2;
  rimRing.position.y = 1.0;
  group.add(rimRing);

  // Handle
  const handle = new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.13, 20, 48, Math.PI * 1.25), ceramic);
  handle.position.set(1.0, 0.0, 0);
  handle.rotation.z = -Math.PI / 2.2;
  group.add(handle);

  // ---- Floating coffee beans -------------------------------------------
  function makeBean() {
    const bean = new THREE.Mesh(new THREE.SphereGeometry(0.34, 20, 16), coffeeMat);
    bean.scale.set(1, 0.66, 0.82);
    // crease
    const crease = new THREE.Mesh(
      new THREE.BoxGeometry(0.52, 0.03, 0.03),
      new THREE.MeshStandardMaterial({ color: 0x1c0d07, roughness: 0.6 })
    );
    crease.position.y = 0.01;
    bean.add(crease);
    return bean;
  }

  const beans = [];
  const beanData = [
    { r: 3.2, a: 0.2, y: 1.4, s: 1.0 },
    { r: 3.8, a: 1.4, y: -0.4, s: 0.8 },
    { r: 3.0, a: 2.6, y: 2.0, s: 0.9 },
    { r: 4.2, a: 3.6, y: 0.6, s: 0.7 },
    { r: 3.5, a: 4.8, y: -1.2, s: 1.1 },
    { r: 4.0, a: 5.8, y: 1.8, s: 0.85 },
  ];
  beanData.forEach((d) => {
    const b = makeBean();
    b.position.set(Math.cos(d.a) * d.r, d.y, Math.sin(d.a) * d.r);
    b.scale.multiplyScalar(d.s);
    b.userData = { angle: d.a, radius: d.r, speed: 0.05 + Math.random() * 0.08, bob: Math.random() * Math.PI * 2 };
    group.add(b);
    beans.push(b);
  });

  // ---- Steam particles --------------------------------------------------
  const steamCount = 60;
  const steamGeo = new THREE.BufferGeometry();
  const steamPos = new Float32Array(steamCount * 3);
  const steamSeed = [];
  for (let i = 0; i < steamCount; i++) {
    const x = (Math.random() - 0.5) * 0.7;
    const z = (Math.random() - 0.5) * 0.7;
    const y = Math.random() * 2.5 + 1.0;
    steamPos[i * 3] = x;
    steamPos[i * 3 + 1] = y;
    steamPos[i * 3 + 2] = z;
    steamSeed.push({ x, z, baseY: y, speed: 0.4 + Math.random() * 0.5, phase: Math.random() * Math.PI * 2 });
  }
  steamGeo.setAttribute("position", new THREE.BufferAttribute(steamPos, 3));
  const steamMat = new THREE.PointsMaterial({
    color: 0xfff2dd,
    size: 0.14,
    transparent: true,
    opacity: 0.35,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const steam = new THREE.Points(steamGeo, steamMat);
  group.add(steam);

  // ---- Interaction ------------------------------------------------------
  const pointer = { x: 0, y: 0 };
  const target = { x: 0, y: 0 };

  window.addEventListener("pointermove", (e) => {
    target.x = (e.clientX / window.innerWidth - 0.5) * 2;
    target.y = (e.clientY / window.innerHeight - 0.5) * 2;
  });

  // ---- Resize -----------------------------------------------------------
  function resize() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize);
  resize();

  // ---- Animate ----------------------------------------------------------
  const clock = new THREE.Clock();
  let running = true;

  function animate() {
    if (!running) return;
    requestAnimationFrame(animate);
    const t = clock.getElapsedTime();

    pointer.x += (target.x - pointer.x) * 0.05;
    pointer.y += (target.y - pointer.y) * 0.05;

    group.rotation.y = t * 0.28 + pointer.x * 0.5;
    group.rotation.x = Math.sin(t * 0.3) * 0.06 + pointer.y * 0.18;
    group.position.y = Math.sin(t * 0.9) * 0.12;

    camera.position.x = pointer.x * 0.8;
    camera.position.y = 1.6 - pointer.y * 0.5;
    camera.lookAt(0, 0.1, 0);

    beans.forEach((b) => {
      const u = b.userData;
      u.angle += u.speed * 0.01;
      b.position.x = Math.cos(u.angle) * u.radius;
      b.position.z = Math.sin(u.angle) * u.radius;
      b.position.y += Math.sin(t * 1.4 + u.bob) * 0.005;
      b.rotation.x += 0.004;
      b.rotation.y += 0.006;
    });

    // steam rise
    const pos = steam.geometry.attributes.position.array;
    for (let i = 0; i < steamCount; i++) {
      const s = steamSeed[i];
      s.baseY += s.speed * 0.008;
      if (s.baseY > 3.6) s.baseY = 1.0;
      pos[i * 3] = s.x + Math.sin(t * 1.5 + s.phase) * 0.18;
      pos[i * 3 + 1] = s.baseY;
      pos[i * 3 + 2] = s.z + Math.cos(t * 1.2 + s.phase) * 0.18;
    }
    steam.geometry.attributes.position.needsUpdate = true;
    steamMat.opacity = 0.32;

    renderer.render(scene, camera);
  }
  animate();

  // Pause when tab hidden / hero scrolled away (performance)
  document.addEventListener("visibilitychange", () => {
    running = !document.hidden;
    if (running) {
      clock.start();
      animate();
    }
  });
})();
