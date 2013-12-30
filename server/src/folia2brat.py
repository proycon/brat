from pynlpl.formats import folia
from annotation import Annotations,SimpleAnnotations,TextAnnotations
import annotation
from message import Messager
from projectconfig import ProjectConfiguration

class ConvertionError(Exception):
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return u'Folia to brat convertion failed: %s' % (text )

def add_attributes(doc, ann, entity_ids):
    attributes = doc.select(folia.Feature)
    events = {}
    triggers = {}
    for i in ann.get_events():
        events[i.trigger] = i
    for attr in attributes:
        p = attr.parent
        #triggers can't have attributes
        if isinstance(p, folia.Entity):
            aid = ann.get_new_id('A')
            if not entity_ids[p.id] in events:
                attribute = annotation.AttributeAnnotation(entity_ids[p.id],aid,attr.subset,"",attr.cls)
            else:
                attribute = annotation.AttributeAnnotation(events[entity_ids[p.id]].id,aid,attr.subset,"",attr.cls)
            ann.add_annotation(attribute)


def build_entity(entity,offsets,full_text,eid, _type =None, alt = False):
    try:
        if entity.cls:
            _type = entity.cls
    except:
        pass
        #_type = entity.cls
    if alt:
        _type = 'alt-'+_type
    brat_entity = annotation.TextBoundAnnotationWithText([(0,0)],eid,_type,"")
    temp_spans = []
    for word in entity.wrefs():
        start, end =0,0
        #This is needed to add an extra space after after a . if the annotation continous over the sentence
        if len(brat_entity.text) >= 2 and brat_entity.text[-2] == "." :
            brat_entity.text += " "

        if not isinstance(word, folia.Morpheme):
            start,end = offsets[word.id]
        else:
            parent = word.parent
            while not isinstance(parent, folia.Word) :
                parent = parent.parent
            start,end = offsets[parent.id]
            text = word.select(folia.TextContent)[0]
            end = start+text.offset+len(text.value)
            start += text.offset
        if not (start == 0 and end ==0):
            temp_spans.append((start,end))
            brat_entity.text = brat_entity.text + str(word)+" "
    spans = []
    if temp_spans:
        span_start,span_end = temp_spans[0]
        for start,end in temp_spans[1:]:
            if start - span_end <= 1 and not full_text[span_end] == '\n':
                span_end = end
            else:
                if full_text[span_end-1] == ".":
                    span_end +=1
                spans.append((span_start,span_end))
                span_start,span_end = start,end
        spans.append((span_start,span_end))
    brat_entity.spans = spans
    return brat_entity


def add_entities(doc,ann,entity_ids,offsets,full_text):
    entities = doc.select(folia.Entity)
    for entity in entities:
        eid = ann.get_new_id('T')
        entity_ids[entity.id]=eid
        brat_entity = build_entity(entity,offsets,full_text,eid)
        if not brat_entity.text =="":
            ann.add_annotation(brat_entity)

def add_comments(doc,ann,entity_ids):
    for entity in doc.select(folia.Entity):
        desc = entity.select(folia.Description)
        if desc:
            #only 1 desc for every entity
            desc = desc[0]
            cid = ann.get_new_id('#')
            description = annotation.OnelineCommentAnnotation(entity_ids[entity.id],cid,"AnnotatorNotes","\t"+desc.value.rstrip())
            ann.add_annotation(description)

def get_entity_id(folia_structure,ann,entity_ids,offsets):
    eid = ""
    aref = folia_structure.select(folia.AlignReference)
    if aref:
        try:
            eid=entity_ids[aref[0].id]
        except:
            eid =""
    return eid

def add_relations(doc,ann,entity_ids,offsets):
    relations = doc.select(folia.Dependency)
    for relation in relations:
        heads= relation.select(folia.Headspan)
        deps= relation.select(folia.DependencyDependent)
        arg1,arg2= "",""
        if(len(heads) == 1 and len(deps) >= 1 and relation.cls == "Event"):
            #event
            trigger = get_entity_id(heads[0],ann,entity_ids,offsets)
            eid = ann.get_new_id('E')
            args =[]
            brat_event = annotation.EventAnnotation(trigger, args, eid, "event","")
            for dep in deps:
                feat = dep.select(folia.Feature)
                role = "target" #default
                if(feat):
                    role=feat[0].cls
                    brat_event.type = feat[0].subset
                eid = get_entity_id(dep,ann,entity_ids,offsets)
                if eid:
                    brat_event.add_argument(role,get_entity_id(dep,ann,entity_ids,offsets))
            if trigger:
                ann.add_annotation(brat_event)
        elif(len(heads) ==1 and len(deps) ==1 and not deps[0].select(folia.Feature)):
            #regular relation
            arg1=get_entity_id(heads[0],ann,entity_ids,offsets)
            arg2=get_entity_id(deps[0],ann,entity_ids,offsets)
            rid = ann.get_new_id('R')
            if arg1 != "" and arg2 != "" :
                brat_relation = annotation.BinaryRelationAnnotation(rid,relation.cls,"Arg1",arg1,"Arg2",arg2,"")
                ann.add_annotation(brat_relation)
        elif(len(heads) >1 and not deps):
            #equiv relation
            entities=[]
            for hd in heads:
                entities.append(get_entity_id(hd,ann,entity_ids,offsets))
            #remove entities without id
            entities=[x for x in entities if x]
            if entities :
                brat_equiv = annotation.EquivAnnotation(relation.cls, entities,"")
                ann.add_annotation(brat_equiv)


def recursive_text(folia_item,txt,offsets):
    for item in folia_item.data:
        if isinstance(item, folia.Paragraph) and txt != "":
            txt = txt+ "\n"
        elif isinstance(item,folia.Sentence) and txt != "":
            txt = txt+ "\n"
        elif isinstance(item,folia.Word) and not item.id in offsets:
            offsets[item.id]= [len(txt), len(txt)+len(str(item))]
            txt = txt + str(item)+" "
        if item.data:
            txt = recursive_text(item, txt, offsets)
    return txt

def parse_text(doc):
    txt= ""
    offsets={}
    for text in doc.data:
        txt += recursive_text(text,txt,offsets)
    return txt,offsets

def make_conf_file(path,ann):
    import os.path
    if os.path.isfile(path+"/annotation.conf"):
        return
    entities = {}
    relations = {}
    equivs = {}
    events = {}
    attributes = {}
    for a in ann.get_entities():
        entities[a.type] = a
    for a in ann.get_relations():
        relations[a.type] = a
    for a in ann.get_equivs():
        equivs[a.type] = a
    for a in ann.get_events():
        events[a.type] = a
    for a in ann.get_attributes():
        try:
            attributes[a.type][a.value] ="1"
        except KeyError:
            attributes[a.type] = {}
            attributes[a.type][a.value] ="1"

    projfile=open (path+"/annotation.conf" , 'w')
    projfile.write("[entities]\n")
    for a in entities:
        projfile.write(a+'\n')
    projfile.write("[relations]\n")
    for a in equivs:
        projfile.write(u'%s\tArg1:<ENTITY>, Arg2:<ENTITY>, <REL-TYPE>:symmetric-transitive\n'%(a))
    for a in relations:
        projfile.write(u'%s\tArg1:<ENTITY>, Arg2:<ENTITY>\n'%(a))
    projfile.write("[events]\n")
    for a in events:
        string = u'%s\t'%(a)
        for i in events[a].args:
            string += str(i[0])+":<ENTITY>, "
        if len(events[a].args)>0:
            string = string[:-2]
        projfile.write(string+'\n')
    projfile.write("[attributes]\n")
    for a in attributes:
        values = attributes[a].keys()
        string = u', Value:%s'%("|".join(values))
        if len(attributes[a].keys()) <= 2 and ( "False" in attributes[a].keys() or "True" in attributes[a].keys() ):
            string = ""
        projfile.write(u'%s\tArg:<ANY>%s\n'%(a,string))
    projfile.close()

def convert(path,fname):
    from message import Messager
    try:
        from os.path import join as path_join
        from document import real_directory
        real_dir = real_directory(path)
    except:
        real_dir=path
    full_path = path_join(real_dir, fname)
    entity_ids = {}
    try:
        doc = folia.Document(file=full_path+".xml")
        temp=open (full_path+".ann" , 'w')
        txt=open (full_path+".txt"  , 'w')
    except IOError as e:
        Messager.error("IOError " +str(e) )
        return { 'result': False, }
    ann_obj = TextAnnotations(full_path)
    text,offsets = parse_text(doc)
    with SimpleAnnotations(ann_obj) as ann:
        add_entities(doc,ann,entity_ids,offsets,text)
        add_relations(doc,ann,entity_ids,offsets)
        add_attributes(doc, ann,entity_ids)
        add_comments(doc,ann,entity_ids)
        try:
            ann.folia=get_extra_info(path,fname)
        except:
            Messager.error("get_extra_info() from folia failed")
            ann.folia= {}
    txt.write(text)
    txt.close()
    #~ temp.write(str(ann))
    #~ temp.close()
    make_conf_file(real_dir,ann)
    #return is needed for client, so it can see the function is done, this can take a few seconds
    return { 'result': True, }

def get_extra_info(path,fname):
    '''
    Methode that converts extra folia annotations
    '''
    try:
        from os.path import join as path_join
        from document import real_directory
        real_dir = real_directory(path)
    except:
        real_dir=path
    path = path_join(real_dir, fname)
    result = {}
    result["entities"] = []
    result["relations"] = []
    result["comments"] = []
    result["attributes"] = []
    result["tokens"] = {}
    try :
        doc = folia.Document(file=path+".xml")
    except:
        return result
    text,offsets = parse_text(doc)
    #TOKEN ANNOTATIONS
    for i in doc.select(folia.Word):
        _id = offsets[i.id][0]
        if not _id in result["tokens"]:
            result["tokens"][_id] = {}
            index = 1
            for j in i.select(folia.Morpheme):
                result["tokens"][_id]['Morpheme'+str(index)]=": " + str(j)
                token_anns = get_token_info(j,'mor'+str(index)+'-')
                string = ""
                for key in token_anns:
                    string += "\n"+key+token_anns[key]
                result["tokens"][_id]['Morpheme'+str(index)]+=string
                j.parent.remove(j)
                index+=1
            if index > 1:
                result["tokens"][_id].update(get_token_info(i,''))
            else:
                result["tokens"][_id] = get_token_info(i,'')
    #ANNOTATIONS REPRESENTED BY AN ENTITY
    entities, relations,comments, attributes = get_extra_entities(offsets,text,doc)
    result["entities"] += entities
    result["relations"] += relations
    result["comments"] += comments
    result["attributes"] += attributes
    return result

def get_token_info(word,pre):
    '''
    Gets all the extra info for a folia word, pre is added in front of key in dictionary, this is to easily add alternative annotations
    '''
    result = {}
    for element in word:
        if isinstance(element, folia.PosAnnotation):
            result[pre+"POS"] =": "+element.cls+get_feature_info(element)
        elif isinstance(element, folia.LemmaAnnotation):
            result[pre+"Lemma"] =": "+element.cls+get_feature_info(element)
        elif isinstance(element, folia.LangAnnotation):
            result[pre+"Lang"] =": "+element.cls+get_feature_info(element)
        elif isinstance(element, folia.DomainAnnotation):
            result[pre+"Domain"] =": "+element.cls+get_feature_info(element)
        elif isinstance(element, folia.SenseAnnotation):
            string = ""
            for a in  element.select(folia.SynsetFeature):
                string += "synset: "+a.cls
            result[pre+"Sense"] =": "+element.cls+" "+string+get_feature_info(element)
        elif isinstance(element, folia.Description):
            result[pre+"Desc"] =": "+element.value+get_feature_info(element)
        elif isinstance(element, folia.Alternative):
            result.update(get_token_info(element,'alt-'))
        elif isinstance(element, folia.Correction):
            if element.hasnew():
                result.update(get_token_info(element.new(),''))
            if element.hassuggestions():
                index = 1
                for sug in element.suggestions():
                    #index is needed to make sure it's an unique key
                    result.update(get_token_info(sug,'sug'+str(index)+'-'))
                    index+=1
        elif isinstance(element, folia.ErrorDetection):
            result[pre+"Error"] =": "+element.cls+get_feature_info(element)
    return result

def get_feature_info(element):
    response =""
    for feat in element.select(folia.Feature):
        response += " "+feat.subset+":"+feat.cls
    return response


def get_id(element,entity_ids):
    eid = ""
    key =""
    aref = element.select(folia.AlignReference)
    if aref:
        try:
            eid=entity_ids[aref[0].id]
        except:
            eid =""
    else:
        for a in element.wrefs():
            key += a.id
        try:
            eid = entity_ids[key]
        except:
            eid =""
    return eid, key

def get_extra_desc(entity,_id):
    desc = entity.select(folia.Description)
    description = None
    if desc and _id:
        #only 1 desc for every entity
        desc = desc[0]
        #if the parent is a word then it will be added as a token annotation
        if not isinstance(desc.parent, folia.Word):
            description = [_id,"AnnotatorNotes","\t"+desc.value.rstrip()]
            #remove it so it won't also be added to a higher element in hierarchy
            desc.parent.remove(desc)
    return description

def get_extra_features(entity, _id,a):
    attributes = entity.select(folia.Feature)
    response = []
    for attr in attributes:
        if not check_if_token_ann(attr) :
            response.append(['AF'+str(a), attr.subset, _id,attr.cls])
            attr.parent.remove(attr)
            a+=1
    return response

def check_if_token_ann(annotation):
    annotation = annotation.parent
    while annotation.parent or isinstance(annotation.parent, folia.Sentence) or isinstance(annotation.parent, folia.Paragraph):
        if isinstance(annotation.parent, folia.Word) or isinstance(annotation.parent, folia.Morpheme):
            return True
        annotation = annotation.parent
    return False

def get_extra_entities(offsets,full_text,doc):
    response = []
    relations = []
    comments = []
    attributes = []
    i=0
    r=0
    a=0
    entity_ids = {}
    #alt is true when it's an alternative layer
    alt = False
    for layer in doc.select(folia.SemanticRolesLayer):
        if isinstance(layer.parent,folia.AlternativeLayers):
            alt = True
        for sem in layer.select(folia.SemanticRole):
            entity = build_entity(sem,offsets,full_text,"TF"+str(i),'sem',alt)
            attributes += get_extra_features(sem, entity.id,len(attributes))
            entity_ids[sem.id] = entity.id
            i+=1
            response.append([unicode(entity.id), entity.type, entity.spans,'semantic',alt])
            desc = get_extra_desc(sem,entity.id)
            if desc:
                comments.append(desc)
        alt = False
    for layer in doc.select(folia.ChunkingLayer):
        if isinstance(layer.parent,folia.AlternativeLayers):
            alt = True
        for chunk in layer.select(folia.Chunk):
            entity = build_entity(chunk,offsets,full_text,"TF"+str(i),'chunk',alt)
            attributes += get_extra_features(chunk, entity.id,len(attributes))
            entity_ids[chunk.id] = entity.id
            i+=1
            response.append([unicode(entity.id), entity.type, entity.spans,'chunk',alt])
            desc = get_extra_desc(chunk,entity.id)
            if desc:
                comments.append(desc)
        alt = False
    for layer in doc.select(folia.CoreferenceLayer):
        if isinstance(layer.parent,folia.AlternativeLayers):
            alt = True
        for coref in layer.select(folia.CoreferenceChain):
            entity = build_entity(coref,offsets,full_text,"TF"+str(i),'coref',alt)
            attributes += get_extra_features(coref, entity.id,len(attributes))
            entity_ids[chunk.id] = entity.id
            i+=1
            response.append([unicode(entity.id), entity.type, entity.spans,'coref',alt])
            desc = get_extra_desc(coref,entity.id)
            if desc:
                comments.append(desc)
        alt = False
    for layer in doc.select(folia.SyntaxLayer):
        if isinstance(layer.parent,folia.AlternativeLayers):
            alt = True
        for su in layer.data:
            if isinstance(su, folia.SyntacticUnit):
                entities=[]
                i = recursive_su(su.cls,su,entities,offsets,full_text,i,entity_ids,comments,attributes,alt)
                for entity in entities:
                    response.append([unicode(entity.id), entity.type, entity.spans,'syntax',alt])
        alt = False
    for layer in doc.select(folia.DependenciesLayer):
        if isinstance(layer.parent,folia.AlternativeLayers):
            alt = True
        for dep in layer.select(folia.Dependency):
            aref = dep.select(folia.AlignReference)
            val =False
            for ref in aref:
                if not isinstance(doc[ref.id],folia.Entity):
                    val=True
                    break
            if val:
                dp = dep.select(folia.DependencyDependent)
                hd = dep.select(folia.Headspan)
                if (len(hd) == 1 and len(dp) == 1):
                    hd = hd[0]
                    dp = dp[0]
                    #key is to test if there is already an entity for this word
                    hdid,hdkey = get_id(hd,entity_ids)
                    dpid,dpkey = get_id(dp,entity_ids)
                    if not hdid:
                        entity1 = build_entity(hd,offsets,full_text,"TF"+str(i),'dependency',alt)
                        entity_ids[hdkey] = entity1.id
                        hdid = entity1.id
                        if entity1.spans:
                            response.append([entity1.id, entity1.type, entity1.spans,'dependency',alt])
                        else:
                            hdid = ""
                    i+=1
                    if not dpid:
                        entity2 = build_entity(dp,offsets,full_text,"TF"+str(i),'dependency',alt)
                        entity_ids[dpkey] = entity2.id
                        dpid = entity2.id
                        if entity2.spans:
                            response.append([entity2.id, entity2.type, entity2.spans,'dependency',alt])
                        else:
                            dpid = ""
                    relation = annotation.BinaryRelationAnnotation("RF"+str(r),dep.cls,"Arg1",hdid,"Arg2",dpid,"")
                    attributes += get_extra_features(dep, hdid,len(attributes))
                    r+=1
                    i+=1
                    if alt:
                        if dpid and hdid:
                            relations.append([relation.id, 'alt-'+str(relation.type), [(relation.arg1l, relation.arg1),(relation.arg2l, relation.arg2)],'dependency',alt])
                            desc = get_extra_desc(dep,relation.id)
                    else:
                        if dpid and hdid:
                            relations.append([relation.id, relation.type, [(relation.arg1l, relation.arg1),(relation.arg2l, relation.arg2)],'dependency',alt])
                            desc = get_extra_desc(dep,relation.id)
                    if desc:
                        comments.append(desc)
        alt = False
    return response, relations, comments, attributes

def recursive_su(string,su,entities,offsets,full_text,i,entity_ids,comments,attributes,alt):
    contains_text = False
    for element in su.data:
        if isinstance(element, folia.SyntacticUnit):
            #string is a ref, so need to edit a copy of the string
            copystring = string
            copystring += ","+element.cls
            i = recursive_su(copystring,element,entities,offsets,full_text,i,entity_ids,comments,attributes,alt)
        if  not contains_text and isinstance(element, folia.Word):
            contains_text = True
    if contains_text:
        entity = build_entity(su,offsets,full_text,"TF"+str(i),string,alt)
        attributes += get_extra_features(su, entity.id,len(attributes))
        entity_ids[su.id] = entity.id
        desc = get_extra_desc(su,entity.id)
        if desc:
            comments.append(desc)
        entities.append(entity)
        i += 1
        for a in su.wrefs():
            su.remove(a)
    return i

if __name__ == '__main__':
    #~ result = get_extra_info("/brat_vb/sentiment/","test")['tokens']
    #~ for i in result:
		#~ print i
    #~ for i in result['entities']:
        #~ print i
    #~ doc = folia.Document(file='/home/hast/Downloads/brat/data/test.xml')
    #~ for i in doc.select(folia.SyntaxLayer):
    import time
    millis = int(round(time.time() * 1000))
    print millis
    convert("/brat_vb/sentiment/","huge")
    millis = int(round(time.time() * 1000)) - millis
    print millis
    print "finish"
