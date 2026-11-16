--[[ The thesis's own pandoc filter, run before pandoc-crossref (which numbers chapters, sections,
figures, tables and equations and resolves references to them, as thesis.yaml configures it).
This filter turns the thesis's own figure kinds into pandoc figures for pandoc-crossref to number:

  ::: {#fig:name plot="file"}          figures/<file>.json drawn by Plotly in HTML,
  Caption text.                        figures/<file>.pdf in LaTeX; the div's text is the caption
  :::
  ::: {#fig:name image="a b" cols="2"} drawings/<name>.svg (Inkscape) inline in HTML, their PDFs
  Caption text.                        in LaTeX, lettered (a), (b), ... when there are several
  :::
  ::: {#fig:name src="path"}           an existing image (a PDF or PNG beside it for LaTeX);
                                       several (src="a b" cols="2") side by side, lettered
  ::: {#fig:name placeholder="text"}   a figure still to be made

and checks that every reference (@sec:, @fig:, @eq:, @tbl:) has a target. References to a
chapter read "Chapter 4": in HTML through pandoc-crossref's per-reference prefix, in LaTeX (where
LaTeX numbers everything) as \ref commands. Citations (@key) are left to --citeproc. ]]

local html = FORMAT:match("html") ~= nil
local latex = FORMAT:match("latex") ~= nil
local targets = {} -- identifier -> true, for every labelled item
local chapters = {} -- identifier -> true, for level-1 headers

local function read(path)
  local file = io.open(path, "r")
  if file == nil then
    error("thesis.lua: no " .. path .. " (run figures.py)")
  end
  local text = file:read("a")
  file:close()
  return text
end

local function caption_of(div)
  local caption = pandoc.List()
  for _, block in ipairs(div.content) do
    if block.t == "Para" or block.t == "Plain" then
      if #caption > 0 then
        caption:insert(pandoc.Space())
      end
      caption:extend(block.content)
    end
  end
  return caption
end

-- the PDF edition's text block (ubonn-thesis on A4 scrbook, as measured with \the\linewidth and
-- \the\textheight), in pt: a figure's panels are scaled to fit it
local LINE, TEXT = 448.13, 609.40

-- a drawing's natural size in pt, from its SVG's width and height (figures/ for TikZ drawings,
-- drawings/ for Inkscape ones), or nil
local function drawing_size(name)
  local units = { pt = 1, mm = 72 / 25.4, cm = 72 / 2.54, ["in"] = 72, px = 0.75, [""] = 0.75 }
  for _, path in ipairs({ "figures/" .. name .. ".svg", "drawings/" .. name .. ".svg" }) do
    local file = io.open(path, "r")
    if file then
      local head = (file:read(4096) or ""):match("<svg[^>]*>") or ""
      file:close()
      local w, wu = head:match('%swidth="([%d.]+)(%a*)"')
      local h, hu = head:match('%sheight="([%d.]+)(%a*)"')
      if w and h then
        return tonumber(w) * (units[wu] or 1), tonumber(h) * (units[hu] or 1)
      end
    end
  end
  return nil
end

-- an image's height over its width, from a PNG's header (other formats: 0.7)
local function aspect(path)
  local file = io.open(path, "rb")
  if file then
    local head = file:read(24) or ""
    file:close()
    if #head == 24 and head:sub(2, 4) == "PNG" then
      local w, h = string.unpack(">I4I4", head, 17)
      return h / w
    end
  end
  return 0.7
end

-- several items side by side in rows of `cols`, lettered (a), (b), ... when there are several,
-- each given as its LaTeX (inside a minipage) and its HTML (inside a panel). Every panel is drawn
-- at one scale, so that lines are equally thick across them: the largest at which the widest row
-- fits the line and the rows fit most of the page, and, for drawings (`natural`), no larger than
-- their own size. `sizes` gives each item's natural width and height.
local gap = 0.02 -- of the line, between panels
local function panels(items, cols, sizes, natural, item_latex, item_html)
  local letter = function(i)
    return #items > 1 and ("(" .. string.char(96 + i) .. ")") or ""
  end
  local usable = 0.995 - gap * (cols - 1) -- slack, as TeX rounds each width to its own unit
  local widest, heights, rows = 0, 0, 0
  for first = 1, #items, cols do
    local sum, tallest = 0, 0
    for i = first, math.min(first + cols - 1, #items) do
      sum = sum + sizes[i][1]
      tallest = math.max(tallest, sizes[i][2])
    end
    widest, heights, rows = math.max(widest, sum), heights + tallest, rows + 1
  end
  local label = #items > 1 and 22 or 8 -- pt per row: its letter and the gap after it
  local scale = math.min(usable * LINE / widest, (0.72 * TEXT - rows * label) / heights)
  if natural then
    scale = math.min(scale, 1)
  end
  local frac = function(i) -- rounded down, so that a row's panels never overflow the line
    return math.floor(1000 * sizes[i][1] * scale / LINE) / 1000
  end
  if latex then
    local parts = {} -- pandoc's figure environment centres its contents
    for i, item in ipairs(items) do
      parts[#parts + 1] = "\\begin{minipage}[b]{" .. string.format("%.3f", frac(i)) .. "\\linewidth}\\centering\n" .. item_latex(item)
        .. (#items > 1 and ("\\\\[0.3ex]{\\small " .. letter(i) .. "}") or "") .. "\n\\end{minipage}"
      if i < #items then
        parts[#parts + 1] = (i % cols == 0) and "\\\\[1.5ex]" or string.format("\\hspace{%.2f\\linewidth}", gap)
      end
    end
    return pandoc.RawBlock("latex", table.concat(parts, "%\n")) -- no spaces between the panels
  end
  local html_parts = { '<div class="panels">' }
  for i, item in ipairs(items) do
    html_parts[#html_parts + 1] = '<div class="panel" style="flex-basis:' .. string.format("%.2f", 100 * frac(i)) .. '%">'
      .. item_html(item) .. (#items > 1 and ('<p class="panel-label">' .. letter(i) .. "</p>") or "") .. "</div>"
    if i % cols == 0 and i < #items then
      html_parts[#html_parts + 1] = '<div class="panel-break"></div>'
    end
  end
  html_parts[#html_parts + 1] = "</div>"
  return pandoc.RawBlock("html", table.concat(html_parts, "\n"))
end

local function words(text)
  local list = pandoc.List()
  for word in text:gmatch("%S+") do
    list:insert(word)
  end
  return list
end

-- drawings (image="a b c", cols="2"): drawings/<name>.svg inline in HTML (build.py fills the
-- placeholders), figures/<name>.pdf in LaTeX, at one scale no larger than their own size
local function drawings(div)
  local names = words(div.attributes.image)
  local sizes = {}
  for i, name in ipairs(names) do
    local w, h = drawing_size(name)
    sizes[i] = { w or LINE, h or 0.7 * LINE }
  end
  return panels(
    names,
    tonumber(div.attributes.cols or "1"),
    sizes,
    true,
    function(name)
      return "\\includegraphics[width=\\linewidth]{figures/" .. name .. ".pdf}"
    end,
    function(name)
      return '<div class="drawing" data-src="drawings/' .. name .. '.svg"></div>'
    end
  )
end

-- an image's file as LaTeX includes it: a PDF, or, without an extension, the PDF or PNG beside it
local function image_file(src)
  if src:match("%.%w+$") then
    return src
  end
  local pdf = io.open(src .. ".pdf", "r")
  if pdf then
    pdf:close()
  end
  return src .. (pdf and ".pdf" or ".png")
end

-- existing images (src="a b", cols="2"): equally wide panels unless the page's height limits them
local function images(div)
  local srcs = words(div.attributes.src)
  local sizes = {}
  for i, src in ipairs(srcs) do
    sizes[i] = { 1000, 1000 * aspect(image_file(src)) }
  end
  return panels(
    srcs,
    tonumber(div.attributes.cols or "1"),
    sizes,
    false,
    function(src)
      return "\\includegraphics[width=\\linewidth]{../" .. image_file(src) .. "}"
    end,
    function(src)
      return '<img class="photo" alt="" data-src="' .. (src:match("%.%w+$") and src or src .. ".png") .. '">'
    end
  )
end

-- plain text made safe inside LaTeX: its special characters escaped
local function latex_text(text)
  local escapes = { ["\\"] = "\\textbackslash{}", ["%"] = "\\%", ["&"] = "\\&", ["#"] = "\\#", ["_"] = "\\_",
    ["{"] = "\\{", ["}"] = "\\}", ["$"] = "\\$", ["^"] = "\\^{}", ["~"] = "\\~{}" }
  return (text:gsub("[\\%%&#_{}%$^~]", escapes))
end

-- a figure div's body: what the figure shows, in the output's own terms
local function body(div)
  local attrs = div.attributes
  if attrs.image then
    return drawings(div)
  end
  if attrs.src then
    return images(div)
  end
  if attrs.placeholder then
    if latex then
      return pandoc.RawBlock("latex", "\\fbox{\\parbox{0.92\\linewidth}{\\centering\\small\\itshape [Figure: " .. latex_text(attrs.placeholder) .. "]}}")
    end
    return pandoc.RawBlock("html", '<div class="placeholder">[Figure: ' .. attrs.placeholder .. "]</div>")
  end
  local name = attrs.plot
  if latex then
    return pandoc.RawBlock("latex", "\\includegraphics[width=\\linewidth]{figures/" .. name .. ".pdf}")
  end
  local spec = read("figures/" .. name .. ".json"):gsub("</", "<\\/")
  return pandoc.RawBlock(
    "html",
    '<div class="plot" id="plot-' .. name .. '"></div>\n'
      .. '<script type="application/json" class="plotly-spec" data-target="plot-' .. name .. '">' .. spec .. "</script>\n"
      .. '<p class="picked" id="picked-' .. name .. '" hidden></p>'
  )
end

-- a display equation followed by {#eq:name}, anywhere in a paragraph: its label noted
local function equation_labels(para)
  local inlines = para.content
  for i, item in ipairs(inlines) do
    if item.t == "Math" and item.mathtype == "DisplayMath" then
      local j = i + 1
      while j <= #inlines and (inlines[j].t == "Space" or inlines[j].t == "SoftBreak") do
        j = j + 1
      end
      local ident = j <= #inlines and inlines[j].t == "Str" and inlines[j].text:match("^{#(eq:[%w%-:]+)}$")
      if ident then
        targets[ident] = true
      end
    end
  end
end

local function table_label(tbl)
  if tbl.identifier ~= "" then
    targets[tbl.identifier] = true
    return
  end
  local caption = tbl.caption.long[1]
  local last = caption and caption.content[#caption.content]
  local ident = last and last.t == "Str" and last.text:match("^{#(tbl:[%w%-:]+)}$")
  if ident then
    targets[ident] = true
  end
end

local function document(doc)
  local blocks = pandoc.List()
  for _, block in ipairs(doc.blocks) do
    if block.t == "Header" then
      if block.identifier ~= "" then
        targets[block.identifier] = true
        if block.level == 1 then
          chapters[block.identifier] = true
        end
      end
      blocks:insert(block)
    elseif block.t == "Div" and block.identifier:match("^fig:") then
      targets[block.identifier] = true
      local caption = pandoc.Caption({ pandoc.Plain(caption_of(block)) })
      blocks:insert(pandoc.Figure({ body(block) }, caption, pandoc.Attr(block.identifier, { "figure" })))
    elseif block.t == "Para" then
      equation_labels(block)
      blocks:insert(block)
    elseif block.t == "Table" then
      table_label(block)
      blocks:insert(html and pandoc.Div({ block }, pandoc.Attr("", { "table-wrap" })) or block)
    else
      blocks:insert(block)
    end
  end
  doc.blocks = blocks
  return doc
end

local commands = { sec = "Section~\\ref{%s}", fig = "Figure~\\ref{%s}", eq = "(\\ref{%s})", tbl = "Table~\\ref{%s}" }

local function reference(cite)
  local first = cite.citations[1]
  local kind = first and first.id:match("^(%a+):")
  if not kind or not commands[kind] then
    return nil
  end
  for _, citation in ipairs(cite.citations) do
    if not targets[citation.id] then
      error("thesis.lua: no " .. citation.id .. " to refer to")
    end
  end
  if #cite.citations ~= 1 then
    return nil
  end
  if latex then
    local command = chapters[first.id] and "Chapter~\\ref{%s}" or commands[kind]
    return pandoc.RawInline("latex", command:format(first.id))
  end
  if chapters[first.id] then
    first.prefix = { pandoc.Str("Chapter") } -- pandoc-crossref puts a space after a custom prefix
    first.mode = "NormalCitation"
    cite.citations = { first }
    return cite
  end
  return nil
end

return { { Pandoc = document }, { Cite = reference } }
