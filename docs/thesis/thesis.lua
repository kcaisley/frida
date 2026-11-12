--[[ The thesis's pandoc filter: numbers chapters, sections, figures and equations, and resolves
their cross-references, for HTML and LaTeX alike (pandoc 2.14 and later).

  # Title {#sec-name}                  a chapter (numbered unless {.unnumbered}); ## a section
  ::: {#fig-name plot="file"}          a figure: figures/<file>.json drawn by Plotly in HTML,
  Caption text.                        figures/<file>.pdf in LaTeX; the div's text is the caption
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

local function number(doc)
  local chapter, section, figures, eqs = 0, 0, 0, 0
  local blocks = pandoc.List()
  for _, block in ipairs(doc.blocks) do
    if block.t == "Header" and not block.classes:includes("unnumbered") and block.level <= 2 then
      local text
      if block.level == 1 then
        chapter, section, figures, eqs = chapter + 1, 0, 0, 0
        text = tostring(chapter)
        labels[block.identifier] = "Chapter " .. text
      else
        section = section + 1
        text = chapter .. "." .. section
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
    else
      blocks:insert(block)
    end
  end
  doc.blocks = blocks
  return doc
end

local commands = { sec = "Section~\\ref{%s}", fig = "Figure~\\ref{%s}", eq = "(\\ref{%s})" }

local function reference(cite)
  if #cite.citations ~= 1 then
    return nil
  end
  local ident = cite.citations[1].id
  local kind = ident:match("^(%a+)%-")
  if not kind or not commands[kind] then
    return nil
  end
  if latex then
    return pandoc.RawInline("latex", commands[kind]:format(ident))
  end
  if not labels[ident] then
    error("thesis.lua: no " .. ident .. " to refer to")
  end
  return pandoc.Link({ pandoc.Str(labels[ident]) }, "#" .. ident, "", pandoc.Attr("", { "xref" }))
end

return { { Pandoc = number }, { Cite = reference } }
