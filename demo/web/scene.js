// The hero: the word DEMO built from paper slips, which the scroll then
// carries through the pipeline - scattered into a corpus, pulled into two
// retrieval lanes, sorted into a ranked column, laid out as a database table
// whose answer row lights up, and finally set into a chat panel like the
// page's own: the question, the agent's two kinds of step, and its answer,
// each arriving in turn. Six poses, blended by scroll position. The scene
// follows the scroll with a short lag so it reads as one motion, and nothing
// animates on its own except a slow idle drift; both are switched off under
// prefers-reduced-motion.
import * as THREE from "three";

const COLORS = {
  aluminum: 0xdce0e5,
  slip: 0xf7f8fa,
  cobalt: 0x2e4bff,
  amber: 0xa8690a,   // the answering row, as on_hold is amber in the results
  violet: 0x7a3cff,  // meaning-search lane, as in the X-ray
  teal: 0x0f9d8a,    // exact-word lane
  steel: 0x7d8794,
  graphite: 0x16191d,
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

  // Lifted so the word sits in the upper part of the stage, clear of the copy.
  const letters = (await glyphPoints("DEMO", 9)).map((p) => p.add(new THREE.Vector3(0, 0.75, 0)));
  const count = letters.length;
  const geometry = new THREE.PlaneGeometry(0.078, 0.102);
  const material = new THREE.MeshStandardMaterial({
    map: slipTexture(), side: THREE.DoubleSide, roughness: 0.65, metalness: 0.05, transparent: true,
  });
  const mesh = new THREE.InstancedMesh(geometry, material, count);
  scene.add(mesh);

  // One "result" subset rides the pipeline to the front; the rest recede.
  // Ten of them form the reranked column, the top three in cobalt.
  // Step 4: twenty-five of them become a 5 x 5 table; the middle row answers.
  // Step 5: sixteen of them become the lines of a chat, set into a panel
  // (buildChat, below).
  const RESULTS = 27, LANE = 4, RANKED = 10, TOP = 3, COLS = 5, ROWS = 5, ANSWER_ROW = 2;
  const order = [...Array(count).keys()].sort(() => Math.random() - 0.5);
  const role = new Array(count).fill(-1);
  order.slice(0, RESULTS).forEach((idx, i) => { role[idx] = i; });

  // ---- step 5: the chat panel -------------------------------------------
  // A panel like the page's own chat: a dark header, the question on the
  // right, then the agent's reply on the left - an order query, a document
  // search, the answer - and the message box. The panel and its plates are
  // real geometry; the lines of text are the same paper slips, which fly in
  // from the table one line at a time as the scroll advances.
  //
  // Everything is laid out in the panel's own units (origin at its centre)
  // and timed in `u`, the scroll's progress through this step (0 to 1).
  const PANEL_W = 1.9, PANEL_H = 2.5, HEADER_H = 0.26, PAD = 0.2;
  const CHAT_SLIP_SCALE = 2.2, SLIP_GAP = 0.21, SLIP_LIFT = 0.07;
  const LEFT = -PANEL_W / 2 + PAD, RIGHT = PANEL_W / 2 - PAD;
  const CHAT_LINES = [
    { size: 3, y: 0.62, side: "right", color: null, at: 0.26 },             // the question
    { size: 4, y: 0.18, side: "left", color: COLORS.amber, at: 0.39 },      // queried orders
    { size: 4, y: -0.26, side: "left", color: COLORS.violet, at: 0.52 },    // searched documents
    { size: 5, y: -0.70, side: "left", color: COLORS.cobalt, at: 0.65 },    // the answer
  ];
  const PANEL_IN = 0.3;        // the panel has risen into place by this point
  const LINE_TIME = 0.22;      // how much scroll one slip's flight takes
  const LINE_STAGGER = 0.025;  // each slip in a line leaves a little after the last
  // Slip number -> where it sits on the panel and when it leaves the table.
  const chatSlots = CHAT_LINES.flatMap((line, row) => Array.from({ length: line.size }, (_, n) => ({
    row, y: line.y, at: line.at + n * LINE_STAGGER,
    x: line.side === "left" ? LEFT + 0.12 + n * SLIP_GAP : RIGHT - 0.12 - (line.size - 1 - n) * SLIP_GAP,
  })));
  const CHAT_SLIPS = chatSlots.length;
  const lineColors = CHAT_LINES.map((line) => (line.color == null ? null : new THREE.Color(line.color)));

  const chat = new THREE.Group();
  chat.visible = false;
  scene.add(chat);
  const plates = [];   // { mesh, at, grow, anchor, size } - revealed as u passes `at`
  function plate(color, w, h, x, y, z, reveal = null) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, 0.03),
      new THREE.MeshStandardMaterial({ color, roughness: 0.7, metalness: 0.05, transparent: true }));
    mesh.position.set(x, y, z);
    chat.add(mesh);
    plates.push({ mesh, x, y, w, h, ...(reveal ?? { at: 0, grow: null }) });
    return mesh;
  }
  // Body, with a dark edge behind it and the header across the top.
  plate(COLORS.graphite, PANEL_W + 0.05, PANEL_H + 0.05, 0, 0, -0.02);
  plate(COLORS.slip, PANEL_W, PANEL_H, 0, 0, 0);
  plate(COLORS.graphite, PANEL_W, HEADER_H, 0, PANEL_H / 2 - HEADER_H / 2, 0.02);
  plate(COLORS.teal, 0.07, 0.07, LEFT - 0.05, PANEL_H / 2 - HEADER_H / 2, 0.04);
  // The question's bubble grows from the right edge; each step's bar grows downward.
  const question = CHAT_LINES[0];
  const bubbleW = question.size * SLIP_GAP + 0.12;
  plate(COLORS.graphite, bubbleW, 0.34, RIGHT - bubbleW / 2, question.y, 0.03, { at: question.at - 0.04, grow: "left" });
  for (const line of CHAT_LINES.slice(1, 3)) {
    plate(line.color, 0.035, 0.32, LEFT - 0.03, line.y, 0.03, { at: line.at - 0.04, grow: "down" });
  }
  // The message box and its send button.
  const boxY = -PANEL_H / 2 + 0.17;
  plate(COLORS.graphite, PANEL_W, 0.03, 0, boxY + 0.17, 0.02);
  plate(COLORS.graphite, 0.34, 0.31, PANEL_W / 2 - 0.17, boxY, 0.02);

  // Where the panel rests. On a wide screen it stands in the right half,
  // turned toward the caption; on a narrow one it is centred above the
  // caption and set back until its width fits.
  const rest = { pos: new THREE.Vector3(), rot: new THREE.Euler() };
  const CAMERA_Z = 5.85, VIEW_X = 0.4;   // the camera's distance and centre line once the story is under way
  function placeChat(aspect) {
    const tan = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    const distance = Math.max(5.4, (PANEL_W / 0.72) / (2 * tan * aspect));
    const viewWidth = 2 * tan * distance * aspect;
    const wide = Math.max(0, Math.min(1, (aspect - 0.8) / 0.5));
    const beside = Math.min(VIEW_X + viewWidth * 0.15, VIEW_X + viewWidth / 2 - PANEL_W / 2 - 0.15);
    rest.pos.set(VIEW_X + (beside - VIEW_X) * wide, 0.65 + (0.1 - 0.65) * wide, CAMERA_Z - distance);
    rest.rot.set(-0.05, -0.1 + (-0.34 + 0.1) * wide, 0);
    // Each chat slip's resting place, a little proud of the panel's face.
    const frame = new THREE.Object3D();
    frame.position.copy(rest.pos); frame.rotation.copy(rest.rot); frame.updateMatrix();
    for (let i = 0; i < count; i++) {
      const k = role[i];
      if (k < 0 || k >= CHAT_SLIPS) continue;
      poses[5][i].pos.set(chatSlots[k].x, chatSlots[k].y, SLIP_LIFT).applyMatrix4(frame.matrix);
      poses[5][i].rot.copy(rest.rot);
    }
  }

  const poses = [[], [], [], [], [], []];
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
    if (k >= 0 && k < COLS * ROWS) {
      // A table seen slightly from the side: rows of cells, flat and aligned.
      const c = k % COLS, row = Math.floor(k / COLS);
      poses[4].push({ pos: new THREE.Vector3(1.0 + (c - 2) * 0.44, 0.95 - row * 0.44, 1.3), rot: new THREE.Euler(-0.2, -0.3, 0),
        scale: row === ANSWER_ROW ? 3.0 : 2.6 });
    } else {
      poses[4].push({ pos: poses[3][i].pos.clone(), rot: poses[3][i].rot, scale: 0.6 });
    }
    if (k >= 0 && k < CHAT_SLIPS) {
      // Placed on the chat panel by placeChat(), which knows the screen's shape.
      poses[5].push({ pos: new THREE.Vector3(), rot: new THREE.Euler(), scale: CHAT_SLIP_SCALE });
    } else {
      poses[5].push({ pos: poses[3][i].pos.clone(), rot: poses[3][i].rot, scale: 0.6 });
    }
    for (const pose of poses) pose[i].scale ??= 1;
  }

  const white = new THREE.Color(COLORS.slip), cobalt = new THREE.Color(COLORS.cobalt);
  const violet = new THREE.Color(COLORS.violet), teal = new THREE.Color(COLORS.teal);
  const amber = new THREE.Color(COLORS.amber);
  const clamp01 = (x) => Math.max(0, Math.min(1, x));
  const tmp = new THREE.Object3D(), qa = new THREE.Quaternion(), qb = new THREE.Quaternion(), col = new THREE.Color();
  const phase = Float32Array.from({ length: count }, () => rand(0, Math.PI * 2));

  const LAST = poses.length - 1;
  const ramp = (x, from, length) => ease(clamp01((x - from) / length));
  let target = 0;   // where the scroll is: 0..5 across the six poses
  let progress = 0; // where the scene is; it follows `target` with a short lag
  let last = 0;
  let fit = 1;      // camera distance multiplier that keeps the word in frame
  function layout(time) {
    // Follow the scroll with a short lag (about a fifth of a second), so a
    // jump of the wheel becomes one continuous move. No lag for reduced motion.
    // A long gap between frames (a hidden tab) simply catches up.
    const dt = time - last; last = time;
    progress = reducedMotion ? target : progress + (target - progress) * (1 - Math.exp(-dt / 180));
    if (Math.abs(target - progress) < 0.0005) progress = target;

    const stage = Math.min(Math.floor(progress), LAST - 1);
    const shared = ease(clamp01(progress - stage));
    const a = poses[stage], b = poses[stage + 1];
    const drift = reducedMotion ? 0 : 1;
    const u = clamp01(progress - (LAST - 1));   // progress through the chat step
    const float = Math.sin(time * 0.0006) * 0.025 * drift;
    layoutChat(u, float);
    for (let i = 0; i < count; i++) {
      // Into the chat, each slip leaves on its own cue and flies an arc toward
      // the viewer before settling on the panel; everything else moves together.
      const k = role[i];
      const flying = stage === LAST - 1 && k >= 0 && k < CHAT_SLIPS;
      const t = flying ? ramp(u, chatSlots[k].at, LINE_TIME) : shared;
      tmp.position.lerpVectors(a[i].pos, b[i].pos, t);
      if (flying) {
        tmp.position.z += Math.sin(Math.PI * t) * 0.55;
        tmp.position.y += float * t;
      }
      tmp.position.y += Math.sin(time * 0.0007 + phase[i]) * 0.02 * drift * (flying ? 1 - t : 1);
      qa.setFromEuler(a[i].rot); qb.setFromEuler(b[i].rot);
      tmp.quaternion.slerpQuaternions(qa, qb, t);
      tmp.scale.setScalar(a[i].scale + (b[i].scale - a[i].scale) * t);
      tmp.updateMatrix();
      mesh.setMatrixAt(i, tmp.matrix);
      // Lanes take their search's colour in step 2, then everything but the
      // top three fades back to paper as the column forms.
      const laneWeight = clamp01(progress - 1.2) * (1 - clamp01(progress - 2));
      col.copy(white);
      if (k >= 0 && k < LANE * 2) col.lerp(k < LANE ? violet : teal, laneWeight);
      // The ranked top three turn cobalt, then hand over to the table's answer row.
      if (k >= 0 && k < TOP) col.lerp(cobalt, clamp01(progress - 2) * (1 - clamp01(progress - 3)));
      if (k >= 0 && Math.floor(k / COLS) === ANSWER_ROW && k < COLS * ROWS) col.lerp(amber, clamp01(progress - 3.2) * (1 - clamp01(progress - 4)));
      // Each line of the chat takes its colour as it lands.
      const line = flying ? lineColors[chatSlots[k].row] : null;
      if (line) col.lerp(line, t);
      mesh.setColorAt(i, col);
    }
    mesh.instanceMatrix.needsUpdate = true;
    mesh.instanceColor.needsUpdate = true;
    // The camera eases in as the word dissolves, then settles on the column.
    // Only the word needs the narrow-screen pull-back; the later poses are
    // laid out for a close camera, so it is released as the word dissolves.
    const zoom = 1 + (fit - 1) * Math.max(0, 1 - progress);
    camera.position.set(Math.sin(progress * 0.6) * 0.8, 0.1, (7.2 - Math.min(progress, 1.5) * 0.9) * zoom);
    camera.lookAt(progress > 2 ? 0.5 * (Math.min(progress, 3) - 2) : 0, 0, 0);
  }

  // The panel rises into place first, then its plates appear on cue: the
  // question's bubble opens from the right, each step's bar draws downward.
  function layoutChat(u, float) {
    chat.visible = u > 0;
    if (!chat.visible) return;
    const risen = ramp(u, 0, PANEL_IN);
    chat.position.copy(rest.pos);
    chat.position.y += (risen - 1) * 1.5 + float;
    chat.position.z -= (1 - risen) * 1.2;
    chat.rotation.set(rest.rot.x - (1 - risen) * 0.9, rest.rot.y - (1 - risen) * 0.5, 0);
    for (const item of plates) {
      const shown = item.grow ? ramp(u, item.at, 0.12) : 1;
      item.mesh.material.opacity = risen * (item.grow ? Math.min(1, shown * 4) : 1);
      if (item.grow === "left") {
        item.mesh.scale.x = Math.max(0.001, shown);
        item.mesh.position.x = item.x + item.w * (1 - shown) / 2;
      } else if (item.grow === "down") {
        item.mesh.scale.y = Math.max(0.001, shown);
        item.mesh.position.y = item.y + item.h * (1 - shown) / 2;
      }
    }
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
    placeChat(camera.aspect);
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

  return { setProgress(p) { target = Math.max(0, Math.min(LAST, p)); } };
}
