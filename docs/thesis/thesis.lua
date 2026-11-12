--[[ The thesis's pandoc filter: numbers chapters, sections, figures and equations, and resolves
their cross-references, for HTML and LaTeX alike (pandoc 2.14 and later).

  # Title {#sec-name}                  a chapter (numbered unless {.unnumbered}); ## a section
  ::: {#fig-name plot="file"}          a figure: figures/<file>.json drawn by Plotly in HTML,
  Caption text.                        figures/<file>.pdf in LaTeX; the div's text is the caption
  :::
  ::: {#fig-name image="a b" cols="2"} a figure of drawings/<name>.svg (Inkscape), lettered
  Caption text.                        (a), (b), ... when there are several
  :::
  $$ ... $$ {#eq-name}                 a numbered equation
  @sec-name  @fig-name  @eq-name       references to them ("Section 1.2", "Figure 1.3", "(1.1)")

Citations (@key) are left to --citeproc, which runs after this filter. ]]

local html = FORMAT:match("html") ~= nil
local latex = FORMAT:match("latex") ~= nil
local labels = {} -- identifier -> its reference text

local function read(path)
  local file = io.open(path, "r")
  if file == nil then
    error("thesis.lua: no " .. path .. " (run figures.py)")
  end
  local text = file:read("a")
  file:close()
  return text
end

-- a figure of drawings (image="a b c", cols="2"): drawings/<name>.svg inline in HTML (build.py
-- fills the placeholders), figures/<name>.pdf in LaTeX; several are lettered (a), (b), ...
local function drawings(div, caption)
  local names = pandoc.List()
  for name in div.attributes.image:gmatch("%S+") do
    names:insert(name)
  end
  local cols = tonumber(div.attributes.cols or "1")
  local letter = function(i)
    return #names > 1 and ("(" .. string.char(96 + i) .. ")") or ""
  end
  if latex then
    local width = string.format("%.3f", 0.98 / cols - 0.01)
    local parts = { "\\begin{figure}[tbp]\n\\centering" }
    for i, name in ipairs(names) do
      parts[#parts + 1] = "\\begin{minipage}[b]{" .. width .. "\\linewidth}\\centering\n\\includegraphics[width=\\linewidth]{figures/" .. name .. ".pdf}"
        .. (#names > 1 and ("\\\\[0.3ex]{\\small " .. letter(i) .. "}") or "") .. "\n\\end{minipage}"
      parts[#parts + 1] = (i % cols == 0 and i < #names) and "\\\\[1.5ex]" or (i < #names and "\\hfill" or "")
    end
    local inlines = pandoc.List({ pandoc.RawInline("latex", "\\caption{") })
    inlines:extend(caption)
    inlines:insert(pandoc.RawInline("latex", "}\\label{" .. div.identifier .. "}"))
    return { pandoc.RawBlock("latex", table.concat(parts, "\n")), pandoc.Plain(inlines), pandoc.RawBlock("latex", "\\end{figure}") }
  end
  local html_parts = { '<div class="panels" style="--cols:' .. cols .. '">' }
  for i, name in ipairs(names) do
    html_parts[#html_parts + 1] = '<div class="panel"><div class="drawing" data-src="drawings/' .. name .. '.svg"></div>'
      .. (#names > 1 and ('<p class="panel-label">' .. letter(i) .. "</p>") or "") .. "</div>"
  end
  html_parts[#html_parts + 1] = "</div>"
  return { pandoc.RawBlock("html", table.concat(html_parts, "\n")) }
end

local function figure(div, number)
  local name = div.attributes.plot
  local caption = pandoc.List()
  for _, block in ipairs(div.content) do
    if block.t == "Para" or block.t == "Plain" then
      if #caption > 0 then
        caption:insert(pandoc.Space())
      end
      caption:extend(block.content)
    end
  end
  if div.attributes.placeholder or div.attributes.src then
    local text = div.attributes.placeholder
    local src = div.attributes.src
    local blocks
    if latex then
      local body
      if src and src:match("%.%w+$") then
        body = "\\includegraphics[width=\\linewidth]{../" .. src .. "}"
      elseif src then
        local pdf = io.open(src .. ".pdf", "r")
        if pdf then
          pdf:close()
        end
        body = "\\includegraphics[width=\\linewidth]{../" .. src .. (pdf and ".pdf" or ".png") .. "}"
      else
        body = "\\fbox{\\parbox{0.92\\linewidth}{\\centering\\small\\itshape [Figure: " .. text .. "]}}"
      end
      local inlines = pandoc.List({ pandoc.RawInline("latex", "\\caption{") })
      inlines:extend(caption)
      inlines:insert(pandoc.RawInline("latex", "}\\label{" .. div.identifier .. "}"))
      return { pandoc.RawBlock("latex", "\\begin{figure}[tbp]\n\\centering\n" .. body), pandoc.Plain(inlines), pandoc.RawBlock("latex", "\\end{figure}") }
    end
    if src then
      blocks = { pandoc.RawBlock("html", '<img class="photo" alt="" data-src="' .. (src:match("%.%w+$") and src or src .. ".png") .. '">') }
    else
      blocks = { pandoc.RawBlock("html", '<div class="placeholder">[Figure: ' .. text .. "]</div>") }
    end
    local label = pandoc.List({ pandoc.Span({ pandoc.Str("Figure " .. number .. ":") }, pandoc.Attr("", { "figlabel" })), pandoc.Space() })
    label:extend(caption)
    blocks[#blocks + 1] = pandoc.Para(label)
    return { pandoc.Div(blocks, pandoc.Attr(div.identifier, { "figure" })) }
  end
  if div.attributes.image then
    local blocks = drawings(div, caption)
    if latex then
      return blocks
    end
    local text = pandoc.List({ pandoc.Span({ pandoc.Str("Figure " .. number .. ":") }, pandoc.Attr("", { "figlabel" })), pandoc.Space() })
    text:extend(caption)
    blocks[#blocks + 1] = pandoc.Para(text)
    return { pandoc.Div(blocks, pandoc.Attr(div.identifier, { "figure" })) }
  end
  if latex then
    local inlines = pandoc.List({ pandoc.RawInline("latex", "\\caption{") })
    inlines:extend(caption)
    inlines:insert(pandoc.RawInline("latex", "}\\label{" .. div.identifier .. "}"))
    return {
      pandoc.RawBlock("latex", "\\begin{figure}[tbp]\n\\centering\n\\includegraphics[width=\\linewidth]{figures/" .. name .. ".pdf}"),
      pandoc.Plain(inlines),
      pandoc.RawBlock("latex", "\\end{figure}"),
    }
  end
  local spec = read("figures/" .. name .. ".json"):gsub("</", "<\\/")
  local raw = '<div class="plot" id="plot-' .. name .. '"></div>\n'
    .. '<script type="application/json" class="plotly-spec" data-target="plot-' .. name .. '">' .. spec .. "</script>\n"
    .. '<p class="picked" id="picked-' .. name .. '" hidden></p>'
  local text = pandoc.List({ pandoc.Span({ pandoc.Str("Figure " .. number .. ":") }, pandoc.Attr("", { "figlabel" })), pandoc.Space() })
  text:extend(caption)
  return { pandoc.Div({ pandoc.RawBlock("html", raw), pandoc.Para(text) }, pandoc.Attr(div.identifier, { "figure" })) }
end

-- a paragraph's display equations followed by {#eq-name}: numbered, labelled
local function equations(para, chapter, count)
  local out = pandoc.List()
  local inlines = para.content
  local i = 1
  while i <= #inlines do
    local item = inlines[i]
    local j = i + 1
    while j <= #inlines and (inlines[j].t == "Space" or inlines[j].t == "SoftBreak") do
      j = j + 1
    end
    local ident = item.t == "Math" and item.mathtype == "DisplayMath" and j <= #inlines and inlines[j].t == "Str" and inlines[j].text:match("^{#(eq%-[%w%-]+)}$")
    if ident then
      count = count + 1
      local number = chapter .. "." .. count
      labels[ident] = "(" .. number .. ")"
      if latex then
        out:insert(pandoc.RawInline("latex", "\\begin{equation}" .. item.text .. "\\label{" .. ident .. "}\\end{equation}"))
      else
        out:insert(pandoc.Span({}, pandoc.Attr(ident, { "eqanchor" })))
        out:insert(pandoc.Math("DisplayMath", item.text .. " \\tag{" .. number .. "}"))
      end
      i = j + 1
    else
      out:insert(item)
      i = i + 1
    end
  end
  para.content = out
  return count
end

-- a table whose caption ends in {#tbl-name}: numbered, labelled
local function table_caption(tbl, number)
  local caption = tbl.caption.long[1]
  if caption == nil then
    return
  end
  local inlines = caption.content
  local last = inlines[#inlines]
  local ident = last and last.t == "Str" and last.text:match("^{#(tbl%-[%w%-]+)}$")
  if not ident then
    return
  end
  inlines:remove(#inlines)
  while #inlines > 0 and (inlines[#inlines].t == "Space" or inlines[#inlines].t == "SoftBreak") do
    inlines:remove(#inlines)
  end
  labels[ident] = "Table " .. number
  tbl.identifier = ident
  if latex then
    inlines:insert(pandoc.RawInline("latex", "\\label{" .. ident .. "}"))
  else
    inlines:insert(1, pandoc.Span({ pandoc.Str("Table " .. number .. ":") }, pandoc.Attr("", { "figlabel" })))
    inlines:insert(2, pandoc.Space())
  end
  return ident
end

local function number(doc)
  local chapter, section, subsection, figures, eqs, tables = 0, 0, 0, 0, 0, 0
  local blocks = pandoc.List()
  for _, block in ipairs(doc.blocks) do
    if block.t == "Header" and not block.classes:includes("unnumbered") and block.level <= 3 then
      local text
      if block.level == 1 then
        chapter, section, subsection, figures, eqs, tables = chapter + 1, 0, 0, 0, 0, 0
        text = tostring(chapter)
        labels[block.identifier] = "Chapter " .. text
      elseif block.level == 2 then
        section, subsection = section + 1, 0
        text = chapter .. "." .. section
        labels[block.identifier] = "Section " .. text
      else
        subsection = subsection + 1
        text = chapter .. "." .. section .. "." .. subsection
        labels[block.identifier] = "Section " .. text
      end
      if html then
        block.content:insert(1, pandoc.Span({ pandoc.Str(text) }, pandoc.Attr("", { "num" })))
        block.content:insert(2, pandoc.Space())
      end
      blocks:insert(block)
    elseif block.t == "Div" and block.identifier:match("^fig%-") then
      figures = figures + 1
      local n = chapter .. "." .. figures
      labels[block.identifier] = "Figure " .. n
      blocks:extend(figure(block, n))
    elseif block.t == "Para" then
      eqs = equations(block, chapter, eqs)
      blocks:insert(block)
    elseif block.t == "Table" then
      local ident = table_caption(block, chapter .. "." .. (tables + 1))
      if ident then
        tables = tables + 1
      end
      if html then
        -- the anchor on a wrapper (pandoc 2.14's HTML drops a table's own id), which also scrolls
        block.identifier = ""
        blocks:insert(pandoc.Div({ block }, pandoc.Attr(ident or "", { "table-wrap" })))
      else
        blocks:insert(block)
      end
    else
      blocks:insert(block)
    end
  end
  doc.blocks = blocks
  return doc
end

local commands = { sec = "Section~\\ref{%s}", fig = "Figure~\\ref{%s}", eq = "(\\ref{%s})", tbl = "Table~\\ref{%s}" }

local function reference(cite)
  if #cite.citations ~= 1 then
    return nil
  end
  local ident = cite.citations[1].id
  local kind = ident:match("^(%a+)%-")
  if not kind or not commands[kind] then
    return nil
  end
  if not labels[ident] then
    error("thesis.lua: no " .. ident .. " to refer to")
  end
  if latex then
    local command = labels[ident]:match("^Chapter") and "Chapter~\\ref{%s}" or commands[kind]
    return pandoc.RawInline("latex", command:format(ident))
  end
  if not labels[ident] then
    error("thesis.lua: no " .. ident .. " to refer to")
  end
  return pandoc.Link({ pandoc.Str(labels[ident]) }, "#" .. ident, "", pandoc.Attr("", { "xref" }))
end

return { { Pandoc = number }, { Cite = reference } }
