# Issues when running CdlOut on designs


```
ERROR (OSSHNL-116): Cannot descend into any of the views defined in the view list 'schematic' specified
for library 'devices' and cell 'log_nmos' for the instance 'Mn2' in cell 'logic/inv_MHthreshold/schematic'. Add
one of these views or modify the view list so that it contains an existing
view.
```

**Fix**: Add `symbol` to the switch view list.



```
*WARNING* (DB-270003): Error kept in "errorDesc" property of the label "pcellEvalFailed" on layer/purpose "marker/error" in the submaster.
*WARNING* (DB-270210): dbOpenCellViewByType: library 'cds_ff_mpt' does not exist
*WARNING* (DB-270329): dbCreateParamInstByMasterName: invalid master id detected.
*WARNING* (DB-270001): Pcell evaluation for BAG_prim/nmos4_lvt/schematic has the following error(s):
*WARNING* (DB-270002): ("dbFindTermByName" 1 t nil ("*Error* dbFindTermByName: argument #1 should be a database object (type template = \"dt\")" nil))
ERROR (OSSHNL-408): Failed to generate the netlist because of a Pcell evaluation error on cellview
'BAG_prim/nmos4_lvt/schematic'. Set simStopNetlistOnPcellFailure to "ignore" to prevent this
error.
```

**Fix**: remove the schematic views for the OA_prim cells, since they contain weird skill code, an they should be netlist primitives anyways for my use.




/****************************************************/
 LIBRARY = "analogLib_tanner"
 CELL    = "nmos4"
/****************************************************/

let( ( libId cellId cdfId )
    unless( cellId = ddGetObj( LIBRARY CELL )
        error( "Could not get cell %s." CELL )
    )
    when( cdfId = cdfGetBaseCellCDF( cellId )
        cdfDeleteCDF( cdfId )
    )
    cdfId  = cdfCreateBaseCellCDF( cellId )

    ;;; Properties
    cdfId->formInitProc            = ""
    cdfId->doneProc                = ""
    cdfId->buttonFieldWidth        = 340
    cdfId->fieldHeight             = 35
    cdfId->fieldWidth              = 350
    cdfId->promptWidth             = 175
    cdfSaveCDF( cdfId )
)



```
*Error*   Cell: log_nmos  in library: devices  is missing a simInfo
          section in it's CDF for the current simulator.
*Error*   Cell: log_pmos  in library: devices  is missing a simInfo
          section in it's CDF for the current simulator.
```

This issue is actually rather complicated. It turns out that the caeleste and tannnerAnalogLib views have no CDF information:

From Tanner analogLib nmos4:
```
/****************************************************/
 LIBRARY = "analogLib_tanner"
 CELL    = "nmos4"
/****************************************************/

let( ( libId cellId cdfId )
    unless( cellId = ddGetObj( LIBRARY CELL )
        error( "Could not get cell %s." CELL )
    )
    when( cdfId = cdfGetBaseCellCDF( cellId )
        cdfDeleteCDF( cdfId )
    )
    cdfId  = cdfCreateBaseCellCDF( cellId )

    ;;; Properties
    cdfId->formInitProc            = ""
    cdfId->doneProc                = ""
    cdfId->buttonFieldWidth        = 340
    cdfId->fieldHeight             = 35
    cdfId->fieldWidth              = 350
    cdfId->promptWidth             = 175
    cdfSaveCDF( cdfId )
)
```

From Caeleste's nmos4:
```
nil
(nil spectre (nil modelParamExprList "" optParamExprList "" opParamExprList "" stringParameters "" propMapping "" termMapping "" termOrder "" componentName "" instParameters "" otherParameters "" netlistProcedure "") hspiceD (nil opParamExprList "" optParamExprList "" propMapping "" termMapping "" termOrder "" namePrefix "" componentName "" instParameters "" otherParameters "" netlistProcedure "") auLvs (nil namePrefix "" permuteRule "" propMapping "" deviceTerminals "" termOrder "" componentName "" instParameters "" otherParameters "" netlistProcedure "") auCdl (nil netlistProcOpts "" dollarEqualParams "" dollarParams "" modelName "" namePrefix "" propMapping "" termOrder "" componentName "" instParameters "" otherParameters "" netlistProcedure "") ams (nil isPrimitive "" extraTerminals "" propMapping "" termMapping "" termOrder "" componentName "" excludeParameters "" arrayParameters "" stringParameters "" referenceParameters "" enumParameters "" instParameters "" otherParameters "" netlistProcedure ""))
(nil paramLabelSet nil opPointLabelSet nil modelLabelSet nil paramDisplayMode nil paramEvaluate "nil nil nil nil nil" paramSimType nil termDisplayMode nil termSimType nil netNameType nil instDisplayMode nil instNameType nil)
(nil doneProc "" formInitProc "" promptWidth 175 fieldWidth nil buttonFieldWidth nil fieldHeight nil)
```

Interestingly, BAG's framework doesn't seem to have anything other than w l and nf:

```
((nil description nil callback nil choices nil defValue "4" display nil dontSave nil editable nil name "w" paramType "string" parseAsCEL nil parseAsNumber nil prompt "w" storeDefault t units nil use nil) (nil description nil callback nil choices nil defValue "10n" display nil dontSave nil editable nil name "l" paramType "string" parseAsCEL nil parseAsNumber nil prompt "l" storeDefault t units nil use nil) (nil description nil callback nil choices nil defValue "1" display nil dontSave nil editable nil name "nf" paramType "string" parseAsCEL nil parseAsNumber nil prompt "nf" storeDefault t units nil use nil))
(nil spectre (nil modelParamExprList "" optParamExprList "" opParamExprList "" stringParameters "" propMapping "" termMapping "" termOrder "" componentName "" instParameters "" otherParameters "" netlistProcedure "") hspiceD (nil opParamExprList "" optParamExprList "" propMapping "" termMapping "" termOrder "" namePrefix "" componentName "" instParameters "" otherParameters "" netlistProcedure "") auLvs (nil namePrefix "" permuteRule "" propMapping "" deviceTerminals "" termOrder "" componentName "" instParameters "" otherParameters "" netlistProcedure "") auCdl (nil netlistProcOpts "" dollarEqualParams "" dollarParams "" modelName "" namePrefix "" propMapping "" termOrder "" componentName "" instParameters "" otherParameters "" netlistProcedure "") ams (nil isPrimitive "" extraTerminals "" propMapping "" termMapping "" termOrder "" componentName "" excludeParameters "" arrayParameters "" stringParameters "" referenceParameters "" enumParameters "" instParameters "" otherParameters "" netlistProcedure ""))
(nil paramLabelSet "w l nf" opPointLabelSet nil modelLabelSet nil paramDisplayMode "parameter" paramEvaluate "nil nil nil nil nil" paramSimType "DC" termDisplayMode "netName" termSimType "DC" netNameType "schematic" instDisplayMode "instName" instNameType "schematic")
(nil doneProc "" formInitProc "" promptWidth 175 fieldWidth 350 buttonFieldWidth 340 fieldHeight 35)
```

Whereas here is a snippet from the CDF dump of analogLib nmos4:

```
    cdfId->simInfo->auCdl = '( nil
        netlistProcedure  ansCdlCompPrim
        instParameters    (m L W)
        componentName     nmos
        termOrder         (D G S B)
        propMapping       (nil L l W w)
        namePrefix        "M"
        modelName         "NM"
    )
```


FIX: Turns out, simply adding W L and nf in the CDF editor then pouplated the full 