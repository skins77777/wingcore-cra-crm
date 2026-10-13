SELECT json_build_object(
 'objects', (SELECT json_agg(json_build_object('id',id,'singular',"nameSingular",'plural',"namePlural",'label',"labelSingular")) FROM core."objectMetadata" WHERE "namePlural" IN ('dingDans','dingDanBianDongs')),
 'fields', (SELECT json_agg(json_build_object('id',f.id,'object',o."nameSingular",'name',f.name,'label',f.label,'type',f.type,'settings',f.settings,'default',f."defaultValue",'options',f.options)) FROM core."fieldMetadata" f JOIN core."objectMetadata" o ON f."objectMetadataId"=o.id WHERE o."namePlural" IN ('dingDans','dingDanBianDongs'))
);

