import maya.cmds as cmds

# アウトライナーで選択中のリファレンスノードを取得
sel_refs = cmds.ls(selection=True, type='reference')

if not sel_refs:
    cmds.warning("アウトライナーでリファレンスを選択してください。")
else:
    for refNode in sel_refs:
        # 選択がリファレンスノード名でない場合に対応
        if not cmds.referenceQuery(refNode, isNodeReferenced=True):
            try:
                loadState = cmds.referenceQuery(refNode, isLoaded=True)
                if not loadState:
                    filePath = cmds.referenceQuery(refNode, filename=True)
                    cmds.file(filePath, removeReference=True)
                    print(u"削除しました：{}".format(filePath))
                else:
                    print(u"スキップ（ロード中）：{}".format(refNode))
            except:
                cmds.warning(u"無効なリファレンスノードをスキップ：{}".format(refNode))
