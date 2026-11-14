import "../../app/globals.css";

import { Flex } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createRoot } from "react-dom/client";

import { DevicePreview } from "@/components/device-preview";
import { DrawableBoardPreview } from "@/components/drawable-board-preview";
import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { resolveBoardModel } from "@/lib/device-preview";

// The app's board wrapper, as the editor renders it: since slice 2.4 a
// BoardViewport, so the flap board scrolls in its bezel instead of shrinking.
const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });

function PreviewFixture() {
  const [drawing, setDrawing] = useState(false);
  const [stroke, setStroke] = useState("");
  return (
    <>
      <button onClick={() => setDrawing(!drawing)}>Toggle drawing</button>
      <output>{stroke}</output>
      {/* Editor content widths from the mobile regression: 302px at 375,
          317px at 390. Keep the real centered-flex/wrapper/preview chain. */}
      <Flex justify="center" data-testid="editor-preview" style={{ width: "calc(100vw - 73px)", marginLeft: 29 }}>
        <DrawableBoardPreview
          active={drawing}
          onStrokePreview={() => {}}
          onStrokeCommit={(cells) => setStroke(JSON.stringify(cells))}
        >
          <DevicePreview
            model={drawing ? null : resolveBoardModel({ device_model: "divoom_pixoo64" })}
            message="HELLO"
            size="md"
          >
            <ScaledBoardDisplay message="HELLO" size="md" isStatic emitCellMetadata />
          </DevicePreview>
        </DrawableBoardPreview>
      </Flex>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={client}>
    <PreviewFixture />
  </QueryClientProvider>,
);
