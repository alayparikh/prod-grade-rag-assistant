// The hero: the word DEMO built from paper slips, which the scroll then
// carries through the pipeline - scattered into a corpus, pulled into two
// retrieval lanes, and sorted into a ranked column. Four poses, blended by
// scroll position; nothing animates on its own except a slow idle drift,
// which is switched off under prefers-reduced-motion.
import * as THREE from "three";

const COLORS = {
  aluminum: 0xdce0e5,
  slip: 0xf7f8fa,
  cobalt: 0x2e4bff,
  steel: 0x7d8794,
};

// Sample points inside the glyphs of `word`, rendered with the page's
// display face, on a regular grid. Returns positions centred on the origin.
async function glyphPoints(word, step) {
  await document.fonts.load('800 200px "Big Shoulders Display"');
  const canvas = document.createElement("canvas");
  canvas.width = 900; canvas.height = 300;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#000";
  ctx.font = '800 290px "Big Shoulders Display"';
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(word, canvas.width / 2, canvas.height / 2 + 12);
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const points = [];
  for (let y = 0; y < canvas.height; y += step) {
    for (let x = 0; x < canvas.width; x += step) {
      if (data[(y * canvas.width + x) * 4 + 3] > 128) {
        points.push(new THREE.Vector3((x - canvas.width / 2) / 100, -(y - canvas.height / 2) / 100, 0));
      }
    }
  }
  return points;
}

// A slip of paper with a header bar and a few ruled lines - a document,
// read at a glance, at any size.
function slipTexture() {
  const c = document.createElement("canvas");
  c.width = 64; c.height = 84;
  const g = c.getContext("2d");
  g.fillStyle = "#16191d"; g.fillRect(0, 0, 64, 84);
  g.fillStyle = "#ffffff"; g.fillRect(4, 4, 56, 76);
  g.fillStyle = "#16191d"; g.fillRect(10, 12, 28, 6);
  g.fillStyle = "#9aa3ae";
  for (let y = 26; y < 74; y += 8) g.fillRect(10, y, y % 16 ? 44 : 34, 3);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

const rand = (a, b) => a + Math.random() * (b - a);
const ease = (t) => t * t * (3 - 2 * t);

export async function mountScene(canvas, { reducedMotion }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(COLORS.aluminum, 9, 40);
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);

  scene.add(new THREE.HemisphereLight(0xffffff, 0x9aa3ae, 2.2));
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(-3, 4, 6);
  scene.add(key);

  // Lifted so the word sits in the upper two-thirds, clear of the copy.
  const letters = (await glyphPoints("DEMO", 9)).map((p) => p.add(new THREE.Vector3(0, 0.45, 0)));
  const count = letters.length;
  const geometry = new THREE.PlaneGeometry(0.078, 0.102);
  const material = new THREE.MeshStandardMaterial({
    map: slipTexture(), side: THREE.DoubleSide, roughness: 0.65, metalness: 0.05, transparent: true,
  });
  const mesh = new THREE.InstancedMesh(geometry, material, count);
  scene.add(mesh);

  // One "result" subset rides the pipeline to the front; the rest recede.
  // Ten of them form the reranked column, the top three in cobalt.
  const RESULTS = 27, LANE = 4, RANKED = 10, TOP = 3;
  const order = [...Array(count).keys()].sort(() => Math.random() - 0.5);
  const role = new Array(count).fill(-1);
  order.slice(0, RESULTS).forEach((idx, i) => { role[idx] = i; });

  const poses = [[], [], [], []];
  for (let i = 0; i < count; i++) {
    const p = letters[i];
    poses[0].push({ pos: new THREE.Vector3(p.x, p.y, rand(-0.06, 0.06)), rot: new THREE.Euler(0, 0, rand(-0.12, 0.12)) });

    const r = rand(2.2, 4.4), th = rand(0, Math.PI * 2), ph = Math.acos(rand(-1, 1));
    const cloud = new THREE.Vector3(r * Math.sin(ph) * Math.cos(th) * 1.5, r * Math.cos(ph) * 0.8, r * Math.sin(ph) * Math.sin(th) - 1);
    poses[1].push({ pos: cloud, rot: new THREE.Euler(rand(-1, 1), rand(-1, 1), rand(-1, 1)) });

    const k = role[i];
    const far = cloud.clone().multiplyScalar(1.6).add(new THREE.Vector3(0, 0, -5));
    if (k >= 0 && k < LANE * 2) {
      // Two lanes: meaning on the left, exact words on the right.
      const side = k < LANE ? -1 : 1, slot = k % LANE;
      // Shifted right of centre: the caption owns the lower left.
      poses[2].push({ pos: new THREE.Vector3(0.75 + side * 0.95, 0.95 - slot * 0.62, 1.2), rot: new THREE.Euler(0, side * -0.35, 0), scale: 3.4 });
    } else if (k >= 0) {
      poses[2].push({ pos: cloud.clone().multiplyScalar(0.9), rot: poses[1][i].rot, scale: 1.4 });
    } else {
      poses[2].push({ pos: far, rot: poses[1][i].rot, scale: 0.7 });
    }

    if (k >= 0 && k < RANKED) {
      // Rank 1 at the top, falling away in depth: a ranked list seen edge-on.
      poses[3].push({ pos: new THREE.Vector3(0.9 + k * 0.05, 1.25 - k * 0.29, 1.4 - k * 0.12), rot: new THREE.Euler(-0.15, -0.55, 0), scale: k < TOP ? 3.3 : 2.5 });
    } else {
      poses[3].push({ pos: far.clone().add(new THREE.Vector3(0, 0, -2)), rot: poses[1][i].rot, scale: 0.6 });
    }
    for (const pose of poses) pose[i].scale ??= 1;
  }

  const white = new THREE.Color(COLORS.slip), cobalt = new THREE.Color(COLORS.cobalt);
  const tmp = new THREE.Object3D(), qa = new THREE.Quaternion(), qb = new THREE.Quaternion(), col = new THREE.Color();
  const phase = Float32Array.from({ length: count }, () => rand(0, Math.PI * 2));

  let progress = 0; // 0..3 across the four poses
  let fit = 1;      // camera distance multiplier that keeps the word in frame
  function layout(time) {
    const stage = Math.min(Math.floor(progress), 2);
    const t = ease(Math.min(1, Math.max(0, progress - stage)));
    const a = poses[stage], b = poses[stage + 1];
    const drift = reducedMotion ? 0 : 1;
    for (let i = 0; i < count; i++) {
      tmp.position.lerpVectors(a[i].pos, b[i].pos, t);
      tmp.position.y += Math.sin(time * 0.0007 + phase[i]) * 0.02 * drift;
      qa.setFromEuler(a[i].rot); qb.setFromEuler(b[i].rot);
      tmp.quaternion.slerpQuaternions(qa, qb, t);
      tmp.scale.setScalar(a[i].scale + (b[i].scale - a[i].scale) * t);
      tmp.updateMatrix();
      mesh.setMatrixAt(i, tmp.matrix);
      const top = role[i] >= 0 && role[i] < TOP;
      col.copy(white).lerp(cobalt, top ? Math.max(0, progress - 2) : 0);
      mesh.setColorAt(i, col);
    }
    mesh.instanceMatrix.needsUpdate = true;
    mesh.instanceColor.needsUpdate = true;
    // The camera eases in as the word dissolves, then settles on the column.
    // Only the word needs the narrow-screen pull-back; the later poses are
    // laid out for a close camera, so it is released as the word dissolves.
    const zoom = 1 + (fit - 1) * Math.max(0, 1 - progress);
    camera.position.set(Math.sin(progress * 0.6) * 0.8, 0.1, (7.2 - Math.min(progress, 1.5) * 0.9) * zoom);
    camera.lookAt(progress > 2 ? 0.5 * (progress - 2) : 0, 0, 0);
  }

  function resize() {
    const { clientWidth: w, clientHeight: h } = canvas;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // Back the camera off on narrow screens until the word's half-width
    // (about 3.4 units) fits, rather than cropping it.
    const halfWidth = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.aspect;
    fit = Math.max(1, 3.6 / (halfWidth * 7.2));
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(canvas);
  resize();

  let visible = true;
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(canvas);
  renderer.setAnimationLoop((time) => {
    if (!visible) return;
    layout(time);
    renderer.render(scene, camera);
  });

  return { setProgress(p) { progress = Math.max(0, Math.min(3, p)); } };
}
