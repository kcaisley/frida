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

-- several items side by side in rows of `cols`, lettered (a), (b), ... when there are several:
-- each item given as its LaTeX (inside a minipage) and its HTML (inside a panel)
local function panels(items, cols, item_latex, item_html)
  local letter = function(i)
    return #items > 1 and ("(" .. string.char(96 + i) .. ")") or ""
  end
  if latex then
    local width = string.format("%.3f", 0.98 / cols - 0.01)
    local parts = {} -- pandoc's figure environment centres its contents
    for i, item in ipairs(items) do
      parts[#parts + 1] = "\\begin{minipage}[b]{" .. width .. "\\linewidth}\\centering\n" .. item_latex(item)
        .. (#items > 1 and ("\\\\[0.3ex]{\\small " .. letter(i) .. "}") or "") .. "\n\\end{minipage}"
      parts[#parts + 1] = (i % cols == 0 and i < #items) and "\\\\[1.5ex]" or (i < #items and "\\hfill" or "")
    end
    return pandoc.RawBlock("latex", table.concat(parts, "\n"))
  end
  local html_parts = { '<div class="panels" style="--cols:' .. cols .. '">' }
  for i, item in ipairs(items) do
    html_parts[#html_parts + 1] = '<div class="panel">' .. item_html(item)
      .. (#items > 1 and ('<p class="panel-label">' .. letter(i) .. "</p>") or "") .. "</div>"
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
-- placeholders), figures/<name>.pdf in LaTeX at their own size, narrowed only to fit
local function drawings(div)
  return panels(
    words(div.attributes.image),
    tonumber(div.attributes.cols or "1"),
    function(name)
      return "\\adjustbox{max width=\\linewidth}{\\includegraphics{figures/" .. name .. ".pdf}}"
    end,
    function(name)
      return '<div class="drawing" data-src="drawings/' .. name .. '.svg"></div>'
    end
  )
end

-- existing images (src="a b", cols="2"): each a PDF (or, without an extension, the PDF or PNG
-- beside the path) in LaTeX, a PNG in HTML (build.py links or embeds it)
local function images(div)
  return panels(
    words(div.attributes.src),
    tonumber(div.attributes.cols or "1"),
    function(src)
      local file = src
      if not src:match("%.%w+$") then
        local pdf = io.open(src .. ".pdf", "r")
        if pdf then
          pdf:close()
        end
        file = src .. (pdf and ".pdf" or ".png")
      end
      return "\\includegraphics[width=\\linewidth]{../" .. file .. "}"
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
