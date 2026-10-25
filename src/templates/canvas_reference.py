"""Shared pixel canvas authoring reference for chat and external MCP clients."""

#: What a pixel board's chat learns about canvases (design PIXEL_CANVAS.md §1).
#: Used by chat and the external MCP authoring reference.
CANVAS_RULES = (
    "PIXEL CANVASES (only when the target display supports pixels)\n"
    "- A page may carry up to 8 `canvases` (create_page / update_page arg):\n"
    "  drawings over a block of character cells, in any RGB colour. One:\n"
    '  {"id": "sky", "area": {"row": 1, "col": 1, "rows": 3, "cols": 8},\n'
    '   "bleed": ["top", "left"], "scale": 1, "text": "flow",\n'
    '   "content": {"size": [32, 16], "background": "#001830",\n'
    '     "palette": {"y": "#ffcc00"}, "shapes": [...], "pixels": ["..yy..", ...]}}\n'
    "- area: 1-based cells; may run past the grid edge (clipped), must\n"
    "  start inside. bleed: sides touching the grid edge reach the panel\n"
    "  border (top/left/right/bottom/all). scale: 1-8 pixels per canvas pixel.\n"
    '  "text": "hide" blanks the cells under it; "flow" wraps text (lines\n'
    "  with wrap on) around it.\n"
    "- content: size = drawing space (scaled to fit; default the canvas\n"
    "  size). Colours: #rgb, #rrggbb, a colour name, a palette key, none.\n"
    '  pixels: rows of palette keys, "." transparent; drawn last.\n'
    '- shapes, drawn in order, each with "type": rect {x,y,w,h,fill,stroke},\n'
    "  circle {cx,cy,r}, ellipse {cx,cy,rx,ry}, line {x1,y1,x2,y2,stroke,width},\n"
    "  polygon {points: [[x,y],...]}, text {x,y,text,color,font: 3x5|5x7},\n"
    "  gradient {from,to,angle; x,y,w,h optional}.\n"
    '- Any field may be a {{...}} expression: "h": "{{= weather.temperature / 4 }}".\n'
    '  "if": "{{...}}" skips a falsy shape; "foreach": "{{plugin.list}}",\n'
    '  "as": "p" repeats it per item (p.field, p.index).\n'
    '- "source": "{{generative_ai_art.canvas}}" draws a plugin variable of\n'
    "  format canvas (a content object) instead of content.\n"
    "- Check with render_page_preview(board_id=..., canvases=...):\n"
    "  canvas_issues name each problem.\n"
)
