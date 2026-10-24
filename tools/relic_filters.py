"""Native filter links and color carriers; never infer categories from names."""
COLORS = ((0, "红色", "Red"), (1, "蓝色", "Blue"),
          (2, "黄色", "Yellow"), (3, "绿色", "Green"))
EDITORS = (0, 2)  # Existing mailbox IDs retained; only one draft per kind is exposed.


def product_index(editor, color):
    if editor not in EDITORS or type(color) is not int or color not in range(4):
        raise ValueError("Invalid relic kind or color")
    return (0 if editor == 0 else 4) + color


def bind_filters(catalog, native):
    if native['source_sha256'] != catalog['source_sha256']:
        raise ValueError('Filter data belongs to another regulation')
    tables=native['tables']
    effects={r['ID']:r for r in tables['AttachEffectParam']}
    filters={r['ID']:r for r in tables['AttachEffectFilterParam']}
    subs={r['ID']:r for r in tables['AttachEffectFilterSubCategoryParam']}
    cats={r['ID']:r for r in tables['AttachEffectFilterCategoryParam']}
    def names(text_id):
        result={lang:values.get(str(text_id),'').strip() for lang,values in native['languages'].items()}
        if not result.get('zhocn'):raise ValueError('Missing native filter label')
        return result
    for entry in catalog['entries']:
        effect=effects.get(entry['effect_id'])
        if effect is None:raise ValueError('Unknown native effect')
        f=filters.get(effect['attachFilterParamId'])
        sub=subs.get(f['attachEffectFilterCategory']) if f and not f['disableParam_NT'] else None
        cat=cats.get(sub['filterCategory']) if sub else None
        entry['filter']=dict(category=cat['ID'],subcategory=sub['ID'],family=f['ID'],
            category_names=names(cat['textId']),subcategory_names=names(sub['textId'])) if cat and cat['textId']>=0 else None
    return catalog


def groups(model, editor, negative=False):
    """A complete partition, including an explicit unclassified fallback."""
    result={}
    for effect_id in model.candidates(editor,negative):
        e=model.entries[effect_id];f=e.get('filter')
        category=f['category'] if f else -1;sub=f['subcategory'] if f else -1
        family=f['family'] if f else effect_id
        cat=result.setdefault(category,dict(names=f['category_names'] if f else {'zhocn':'其他／未分类','engus':'Other / unclassified'},subcategories={}))
        child=cat['subcategories'].setdefault(sub,dict(names=f['subcategory_names'] if f else {'zhocn':'其他词条','engus':'Other effects'},families={}))
        child['families'].setdefault(family,[]).append(effect_id)
    return result


def color_products(native):
    rows={r['ID']:r for r in native['tables']['EquipParamAntique']}
    output=[]
    for editor,ids in ((0,(102,111,120,129)),(2,(2000002,2000102,2000202,2000302))):
        for color,template in enumerate(ids):
            row=rows[template]
            if row['relicColor']!=color or row['isDeepRelic']!=(editor==2) or row['attachEffectTableId_3']<0:
                raise ValueError('Unexpected native three-effect color template')
            index=product_index(editor,color)
            output.append(dict(id=9000000+index,shop_id=1900200000+index,editor=editor,color=color,template_id=template,icon_id=row['iconId']))
    return output
