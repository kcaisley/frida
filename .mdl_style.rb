all

rule 'MD007', :indent => 2
rule 'MD013', :line_length => 120, :ignore_code_blocks => true, :tables => false
rule 'MD029', :style => :ordered
rule 'MD033', :allowed_elements => 'br,img,p'
rule 'MD046', :style => :fenced

# rumdl checks these rules. mdl's older parser disagrees with CommonMark on
# several valid constructs, so avoid reporting the same documents differently.
exclude_rule 'MD002'
exclude_rule 'MD024'
exclude_rule 'MD041'
exclude_rule 'MD005'
exclude_rule 'MD007'
