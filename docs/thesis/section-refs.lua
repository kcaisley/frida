--[[ Runs after --citeproc: the reference list split by section. Each section (each ## heading, and a
chapter's text before its first section) ends with the references it cites, numbered as citeproc
numbered them for the whole thesis; its citations link to that list. The thesis-wide list is
dropped. ]]

local function entries(refs)
  local by_id = {}
  for _, block in ipairs(refs.content) do
    if block.t == "Div" and block.identifier:match("^ref%-") then
      by_id[block.identifier:sub(5)] = block
    end
  end
  return by_id
end

-- the keys a run of blocks cites, in order of first citation
local function cited(blocks)
  local keys, seen = {}, {}
  pandoc.walk_block(pandoc.Div(blocks), {
    Cite = function(cite)
      for _, c in ipairs(cite.citations) do
        if not seen[c.id] then
          seen[c.id] = true
          keys[#keys + 1] = c.id
        end
      end
    end,
  })
  return keys
end

local function number_of(entry)
  return tonumber(pandoc.utils.stringify(entry):match("^%[(%d+)%]")) or math.huge
end

local function split(doc)
  local refs
  local body = pandoc.List()
  for _, block in ipairs(doc.blocks) do
    if block.t == "Div" and block.identifier == "refs" then
      refs = block
    elseif not (block.t == "Header" and block.identifier == "bibliography") then
      body:insert(block)
    end
  end
  if refs == nil then
    return nil
  end
  local by_id = entries(refs)
  local out, section, count = pandoc.List(), pandoc.List(), 0

  local function close()
    local list = pandoc.List()
    for _, key in ipairs(cited(section)) do
      if by_id[key] then
        list:insert(by_id[key])
      end
    end
    if #list > 0 then
      table.sort(list, function(a, b)
        return number_of(a) < number_of(b)
      end)
      count = count + 1
      local suffix = "-s" .. count
      local relink = {
        Link = function(link)
          local key = link.target:match("^#ref%-(.+)$")
          if key then
            link.target = "#ref-" .. key .. suffix
            return link
          end
        end,
      }
      for i, block in ipairs(section) do
        section[i] = pandoc.walk_block(block, relink)
      end
      local copies = pandoc.List()
      for _, entry in ipairs(list) do
        copies:insert(pandoc.Div(entry.content, pandoc.Attr(entry.identifier .. suffix, entry.classes)))
      end
      section:insert(pandoc.Div({
        pandoc.Para({ pandoc.Str("References") }),
        pandoc.Div(copies, pandoc.Attr("", { "references", "csl-bib-body" })),
      }, pandoc.Attr("", { "section-refs" })))
    end
    out:extend(section)
    section = pandoc.List()
  end

  for _, block in ipairs(body) do
    if block.t == "Header" and block.level <= 2 then
      close()
    end
    section:insert(block)
  end
  close()
  doc.blocks = out
  return doc
end

return { { Pandoc = split } }
