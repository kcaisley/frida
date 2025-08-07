function fixUnicode(text)
  -- Replace common Unicode characters with LaTeX equivalents
  text = string.gsub(text, "μ", "\\mu ")
  return text
end

function Table(elem)
  -- Convert longtable to simple table
  local headers = {}
  local rows = {}
  
  -- Extract headers
  for i, cell in pairs(elem.head.rows[1].cells) do
    table.insert(headers, fixUnicode(pandoc.utils.stringify(cell.contents)))
  end
  
  -- Extract rows
  for _, row in pairs(elem.bodies[1].body) do
    local row_data = {}
    for _, cell in pairs(row.cells) do
      table.insert(row_data, fixUnicode(pandoc.utils.stringify(cell.contents)))
    end
    table.insert(rows, row_data)
  end
  
  -- Create simple LaTeX tabular
  local latex_code = "\\begin{table}[h!]\n\\centering\n\\begin{tabular}{cccc}\n\\toprule\n"
  
  -- Add headers with math mode
  local formatted_headers = {}
  for i, header in pairs(headers) do
    if string.find(header, "\\") then
      -- Contains LaTeX commands, wrap in math mode
      formatted_headers[i] = "$" .. header .. "$"
    else
      formatted_headers[i] = header
    end
  end
  latex_code = latex_code .. table.concat(formatted_headers, " & ") .. " \\\\\n\\midrule\n"
  
  -- Add rows with math mode for LaTeX expressions
  for _, row in pairs(rows) do
    local formatted_row = {}
    for i, cell in pairs(row) do
      if string.find(cell, "\\") then
        -- Contains LaTeX commands, wrap in math mode
        formatted_row[i] = "$" .. cell .. "$"
      else
        formatted_row[i] = cell
      end
    end
    latex_code = latex_code .. table.concat(formatted_row, " & ") .. " \\\\\n"
  end
  
  latex_code = latex_code .. "\\bottomrule\n\\end{tabular}\n\\end{table}\n"
  
  return pandoc.RawBlock('latex', latex_code)
end