import maya.cmds as cmds
allFilePath = cmds.file(q =True ,reference =True)

for filePath in allFilePath:
    referenceNode = cmds.file(filePath,q =True ,referenceNode = True)
    loadState = cmds.referenceQuery(referenceNode,isLoaded=True)

    if loadState == False:
        cmds.file(filePath, removeReference=True)
        
