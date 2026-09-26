import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const { SKILL_DIR, TMP_DIR, WORKSPACE_DIR, RUNTIME_PYTHON } = process.env;
for (const [name, value] of Object.entries({ SKILL_DIR, TMP_DIR, WORKSPACE_DIR, RUNTIME_PYTHON })) {
  if (!path.isAbsolute(value ?? "")) throw new Error(`${name} must be an absolute path`);
}

const { finalizePresentation } = await import(
  pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href,
);
const assetDir = path.join(WORKSPACE_DIR, "examples", "public-demo");
const backgroundPath = path.join(assetDir, "binary-classification-background.png");
const background = new Uint8Array(await fs.readFile(backgroundPath));
const fontFamily = "Arial";

const rounds = [
  {
    slug: "round-1",
    title: "Binary Classification · Round 1",
    slides: [
      {
        title: "Learning goal",
        body: "Predict label 0 or 1 from input features.",
        narration: "This is a synthetic classroom recording created for the Classroom Review Agent public demo. In binary classification, our learning goal is to predict label zero or one from input features. We fit the model on labeled training examples.",
      },
      {
        title: "Decision threshold",
        body: "Probability ≥ 0.50 gives label 1\nProbability < 0.50 gives label 0",
        narration: "The model returns a probability. We use a decision threshold of zero point five. A probability at or above zero point five becomes label one. A lower probability becomes label zero.",
      },
      {
        title: "Quick check",
        body: "The model score is 0.72. Which label?\n\nAnswer: label 1",
        narration: "Here is a quick check. The model score is zero point seven two. Which label should we predict? The answer is label one because the score is above the threshold. We will move on immediately.",
      },
    ],
  },
  {
    slug: "round-2",
    title: "Binary Classification · Round 2",
    slides: [
      {
        title: "Learning goal and success check",
        body: "Choose a label and explain the threshold rule.",
        narration: "This is the second synthetic round. By the end, learners should choose a binary label and explain how the threshold supports the choice. The explanation is part of the success check.",
      },
      {
        title: "Think, compare, explain",
        body: "Scores: 0.72 and 0.31\n\nThink silently, compare, then explain.",
        narration: "Consider two model scores: zero point seven two and zero point three one. First think silently. Then compare your labels with a partner. Explain why each score falls on one side of the zero point five threshold. I will pause before sharing the answer.",
      },
      {
        title: "Reasoning check",
        body: "0.72 gives label 1\n0.31 gives label 0\n\nWhat changes at threshold 0.80?",
        narration: "Now check the reasoning. Zero point seven two gives label one, and zero point three one gives label zero. If the threshold changed to zero point eight, the first prediction would also become label zero. Write one sentence explaining why.",
      },
    ],
  },
];

await fs.mkdir(TMP_DIR, { recursive: true });

for (const round of rounds) {
  const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  const previewDir = path.join(TMP_DIR, round.slug);
  await fs.mkdir(previewDir, { recursive: true });

  for (const [index, content] of round.slides.entries()) {
    const slide = presentation.slides.add();
    slide.background.fill = "#F7F2E8";
    slide.images.add({
      blob: background,
      contentType: "image/png",
      alt: "Abstract binary-classification decision boundary with two groups of points",
      fit: "cover",
      position: { left: 0, top: 0, width: 1280, height: 720 },
      prompt: "Project-generated abstract binary classification background without text or logos",
    });
    const title = slide.shapes.add({
      geometry: "textbox",
      position: { left: 82, top: 105, width: 690, height: 100 },
      fill: "none",
      line: { fill: "none", width: 0 },
    });
    title.text = content.title;
    title.text.style = {
      typeface: fontFamily,
      fontSize: 44,
      bold: true,
      color: "#17324D",
      autoFit: "shrinkText",
    };
    const body = slide.shapes.add({
      geometry: "textbox",
      position: { left: 84, top: 245, width: 635, height: 285 },
      fill: "none",
      line: { fill: "none", width: 0 },
    });
    body.text = content.body;
    body.text.style = {
      typeface: fontFamily,
      fontSize: 29,
      color: "#243B53",
      autoFit: "shrinkText",
    };
    const footer = slide.shapes.add({
      geometry: "textbox",
      position: { left: 84, top: 632, width: 440, height: 30 },
      fill: "none",
      line: { fill: "none", width: 0 },
    });
    footer.text = `Synthetic public demo · ${index + 1}/3`;
    footer.text.style = {
      typeface: fontFamily,
      fontSize: 15,
      color: "#66788A",
      autoFit: "none",
    };
    slide.speakerNotes.textFrame.setText(
      `Synthetic public demo material. Licensed CC BY 4.0. Narration: ${content.narration}`,
    );
    const preview = await presentation.export({ slide, format: "png", scale: 1 });
    await fs.writeFile(
      path.join(previewDir, `slide-${index + 1}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }

  const candidatePath = path.join(TMP_DIR, `${round.slug}-candidate.pptx`);
  await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
  const finalPath = path.join(assetDir, `${round.slug}-courseware.pptx`);
  await finalizePresentation({
    explicitTotalSlideCount: 3,
    requiredNativeTableOwnerSlides: [],
    requiredNativeChartOwnerSlides: [],
    workspaceDir: WORKSPACE_DIR,
    candidatePath,
    finalPath,
    pythonExecutable: RUNTIME_PYTHON,
    integrityValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_package_integrity.py"),
    layoutValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_layout_geometry.py"),
    layoutArgs: [
      "--expected-slide-size-emu", "12192000,6858000",
      "--validate-heading-fit",
    ],
    fontPolicy: { basis: "design", families: [fontFamily] },
    verifyArtifactToolImport: true,
    receiptPath: path.join(TMP_DIR, `${round.slug}.validation.json`),
  });
}

await fs.writeFile(
  path.join(TMP_DIR, "narration.json"),
  JSON.stringify(
    rounds.map((round) => ({
      slug: round.slug,
      narration: round.slides.map((slide) => slide.narration),
    })),
    null,
    2,
  ),
);
