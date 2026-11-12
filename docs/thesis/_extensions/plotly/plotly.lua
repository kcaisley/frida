-- {{< plotly NAME >}}: one of figures.py's figures. The web edition embeds figures/NAME.json for
-- Plotly to draw (plotly.html); every other format includes figures/NAME.pdf. Place it inside a
-- figure div (::: {#fig-...} ... caption ... :::) so either edition numbers and captions it.

local function read(path)
  local file = io.open(path, "r")
  if file == nil then
    error("plotly shortcode: no " .. path .. " (run docs/thesis/figures.py)")
  end
  local text = file:read("a")
  file:close()
  return text
end

return {
  ["plotly"] = function(args)
    local name = pandoc.utils.stringify(args[1])
    local root = quarto.project.directory or "."
    if quarto.doc.is_format("html") then
      local spec = read(root .. "/figures/" .. name .. ".json"):gsub("</", "<\\/")
      local id = "plotly-" .. name
      return pandoc.RawBlock(
        "html",
        '<div class="plotly-figure" id="' .. id .. '" role="img"></div>\n'
          .. '<script type="application/json" class="plotly-spec" data-target="' .. id .. '">'
          .. spec
          .. "</script>"
      )
    end
    return pandoc.Para({ pandoc.Image({}, "figures/" .. name .. ".pdf", "", { width = "100%" }) })
  end,
}
