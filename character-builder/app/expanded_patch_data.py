"""Source edits that add the CUSTOM page of native-donor fighters to Tekken 3 Expanded."""
R = "src/tekken3_ttt1_roster.c"
M = "src/tekken3_ttt1_mod.c"
C = "src/tekken3_ttt1_combat.c"
N = "src/tekken3_native_moves.c"
EXPANDED_ROSTER = R

ROSTER = [
# --- limits and the guest record ---
("enum { GUEST_MAX=18 };",
 "/* Tekken 3 Character Builder: custom fighters (customs.txt) follow the TTT1\n"
 " * guests in the roster, on a third CUSTOM page. Each takes a Tekken 3\n"
 " * fighter's model, moves and profiles (its donor). At most 12, so their IDs\n"
 " * (41..52) keep availability bits 9..20, which the stock roster unlocks. */\n"
 "enum { TAG_MAX=18, CUSTOM_MAX=12, GUEST_MAX=TAG_MAX+CUSTOM_MAX };", 1),
("    unsigned char *ui;\n",
 "    unsigned char *ui;\n"
 "    int custom;                   /* Character Builder fighter: native model and moves */\n"
 "    unsigned donor_id;            /* its Tekken 3 donor (0..20) */\n"
 "    unsigned music_owner;         /* T3CB-PATCH-17: the Tekken 3 fighter whose music it takes */\n", 1),
("static unsigned roster_count;\n",
 "static unsigned roster_count;\n"
 "/* roster[0..tag_count) are the TTT1 guests (Tag page), the rest custom fighters. */\n"
 "static unsigned tag_count;\n"
 "static int page,grid_page;\n"
 "static unsigned page_first(int p){return p==2?tag_count:0;}\n"
 "static unsigned page_len(int p){return p==2?roster_count-tag_count:(p?tag_count:0);}\n"
 "static int page_total(void){return roster_count>tag_count?3:2;}\n"
 "static int guest_page(unsigned k){return k>=tag_count?2:1;}\n"
 "static const char *page_name(int p){return p==2?\"Custom\":p?\"Tag\":\"Tekken 3\";}\n"
 "", 1),
# --- page-relative Tag layout ---
("static unsigned tag_cols(void){return roster_count>TAG_BASE?TAG_BASE_COLS+1:TAG_BASE_COLS;}",
 "static unsigned tag_cols(void){return page_len(page)>TAG_BASE?TAG_BASE_COLS+1:TAG_BASE_COLS;}", 1),
("static int tag_guest_at(unsigned col,unsigned row) {\n    for(unsigned k=0;k<roster_count;k++) {",
 "static int tag_guest_at(unsigned col,unsigned row) {\n    for(unsigned k=0;k<page_len(page);k++) {", 1),
# --- loading custom fighters ---
("static void add_guest(const char *key) {\n    if(roster_index(key)>=0)return;\n    if(roster_count>=GUEST_MAX){",
 "static void add_guest(const char *key) {\n    if(roster_index(key)>=0)return;\n    if(roster_count>=TAG_MAX){", 1),
("    g->catalog_index=roster_count++;\n}\n",
 "    g->catalog_index=roster_count++;\n}\n"
 "/* Custom fighters: <asset root>/customs.txt, one \"<key> <donor ID>\" per line,\n"
 " * optionally followed by the fighters whose stage and music it takes (T3CB-PATCH-17),\n"
 " * with <Key>-T3-ui.jui, <Key>-T3-name.4bpp and <Key>-T3-label.txt beside it. */\n"
 "static unsigned custom_slot_model(unsigned k,unsigned c);   /* T3CB-PATCH-9 */\n"
 "static void add_customs(void) {\n"
 "    const char *root=tekken3_ttt1_asset_root();char path[4096];\n"
 "    if(!root || snprintf(path,sizeof path,\"%s/customs.txt\",root)>=(int)sizeof path)return;\n"
 "    FILE *f=fopen(path,\"rb\");if(!f)return;\n"
 "    char line[96];\n"
 "    while(fgets(line,sizeof line,f)) {\n"
 "        char key[32],style[32];unsigned donor=99,stage=99,music=99;int like=-1;\n"
 "        if(sscanf(line,\"%31s %31s %u %u\",key,style,&stage,&music)<2 || roster_index(key)>=0)continue;\n"
 "        /* T3CB-PATCH-23: \"@<guest key>\" makes a fighter on a TTT1 guest's style: the guest's\n"
 "         * model, moves and data (its data prefix), the fighter's own name, portrait and plate. */\n"
 "        if(style[0]=='@'){like=roster_index(style+1);if(like<0 || (unsigned)like>=tag_count)continue;}\n"
 "        else{char *end;unsigned long d=strtoul(style,&end,10);if(*end || d>20)continue;donor=(unsigned)d;}\n"
 "        if(roster_count-tag_count>=CUSTOM_MAX){fprintf(stderr,\"Custom fighters: %s left out, the Custom page holds %u\\n\",key,(unsigned)CUSTOM_MAX);continue;}\n"
 "        Tekken3Guest *g=&roster[roster_count];\n"
 "        memset(g,0,sizeof *g);\n"
 "        if(!describe(g,key) || !load_ui(g)){\n"
 "            fprintf(stderr,\"Custom fighters: %s left out, its interface files failed validation\\n\",key);\n"
 "            free(g->ui);memset(g,0,sizeof *g);continue;\n"
 "        }\n"
 "        if(like>=0) {                                   /* T3CB-PATCH-23: a guest in all but looks */\n"
 "            const Tekken3Guest *s=&roster[like];\n"
 "            memcpy(g->data_prefix,s->data_prefix,sizeof g->data_prefix);\n"
 "            memcpy(g->donor_prefix,s->donor_prefix,sizeof g->donor_prefix);\n"
 "            memcpy(g->donor_moveset,s->donor_moveset,sizeof g->donor_moveset);\n"
 "            g->moveset=s->moveset;g->donor_count=s->donor_count;g->on_button=s->on_button;\n"
 "            g->third_costume=s->third_costume;g->donor_id=23u+(unsigned)like;   /* the guest's ID (strips) */\n"
 "            g->arena_owner=stage<=20?stage:s->arena_owner;g->music_owner=music<=20?music:s->arena_owner;\n"
 "            g->catalog_index=roster_count++;\n"
 "            fprintf(stderr,\"Custom fighters: %s (character %u) fights as %s\\n\",g->name,23u+g->catalog_index,s->name);\n"
 "            continue;\n"
 "        }\n"
 "        g->custom=1;g->donor_id=donor;g->moveset=NO_MOVESET;\n"
 "        g->arena_owner=stage<=20?stage:donor;g->music_owner=music<=20?music:donor;\n"
 "        g->third_costume=0;g->donor_count=0;\n"
 "        g->catalog_index=roster_count++;\n"
 "        /* T3CB-PATCH-9: Start picks costume 3 when it has a model (the donor's or a variant's). */\n"
 "        g->third_costume=custom_slot_model(g->catalog_index,2)!=255;\n"
 "        fprintf(stderr,\"Custom fighters: %s (character %u) fights as character %u\\n\",g->name,23u+g->catalog_index,donor);\n"
 "    }\n"
 "    fclose(f);\n"
 "}\n", 1),
("    if(!roster_count)add_guest(\"jun\");\n",
 "    if(!roster_count)add_guest(\"jun\");\n"
 "    tag_count=roster_count;\n"
 "    add_customs();\n", 1),
# --- donors ---
("int tekken3_guest_character(unsigned id) {\n    return id>=GUEST_ID && id<GUEST_ID+roster_count?(int)(id-GUEST_ID):-1;\n}\n",
 "int tekken3_guest_character(unsigned id) {\n    return id>=GUEST_ID && id<GUEST_ID+roster_count?(int)(id-GUEST_ID):-1;\n}\n"
 "/* A custom fighter's Tekken 3 donor for a character ID, else -1. */\n"
 "int tekken3_guest_native(unsigned id) {\n"
 "    int k=tekken3_guest_character(id);\n"
 "    return k>=0 && roster[k].custom?(int)roster[k].donor_id:-1;\n"
 "}\n"
 "/* The stock fighter whose tables a guest reads: Jin's for TTT1 guests. */\n"
 "static unsigned guest_donor(unsigned id){int d=tekken3_guest_native(id);return d<0?9u:(unsigned)d;}\n"
 "/* The same, for the character-data remaps, noting once which donor a custom fighter reads. */\n"
 "static unsigned remap_donor(unsigned id) {\n"
 "    static unsigned long long logged;\n"
 "    int d=tekken3_guest_native(id);\n"
 "    if(d>=0 && id<64 && !(logged>>id&1)){logged|=1ull<<id;fprintf(stderr,\"Custom fighters: character %u reads character %d's data\\n\",id,d);}\n"
 "    return d<0?9u:(unsigned)d;\n"
 "}\n"
 "static unsigned custom_slot_model(unsigned k,unsigned c);   /* T3CB-PATCH-9 */\n", 1),
("static uint32_t guest_desc(unsigned k){return desc+k*DESC_STRIDE;}",
 "/* 22 records fit before name_table; the rest follow its 64 entries. */\n"
 "static uint32_t guest_desc(unsigned k){return k<22?desc+k*DESC_STRIDE:name_table+NAME_TABLE_IDS*4+(k-22)*DESC_STRIDE;}", 1),
("        psx_mod_write_word(body_profiles+(GUEST_ID+k)*4,psx_mod_read_word(0x80096f60+9*4));",
 "        psx_mod_write_word(body_profiles+(GUEST_ID+k)*4,psx_mod_read_word(0x80096f60+(roster[k].custom?roster[k].donor_id:9)*4));", 1),
("            psx_mod_write_byte(model_map+(GUEST_ID+k)*4+c,GUEST_MODEL);",
 "            psx_mod_write_byte(model_map+(GUEST_ID+k)*4+c,roster[k].custom?\n"
 "                custom_slot_model(k,c):GUEST_MODEL);", 1),
("tekken3_guest_character(cpu->gpr[5])>=0)cpu->gpr[5]=9;",
 "tekken3_guest_character(cpu->gpr[5])>=0)cpu->gpr[5]=remap_donor(cpu->gpr[5]);", 2),
# A custom fighter starts from its donor's own descriptor (T3CB-PATCH-2): bytes 6..8,
# whose meaning is not known yet, then match the donor instead of Jin.
("        copy_guest(d,0x80022274,12);\n",
 "        /* T3CB-PATCH-2: a custom fighter copies its donor's descriptor, not Jin's. */\n"
 "        uint32_t from=roster[k].custom?psx_mod_read_word(0x80097d40+roster[k].donor_id*16):0x80022274;\n"
 "        copy_guest(d,from,12);\n"
 "        if(roster[k].custom)fprintf(stderr,\"Custom fighters: %s descriptor from character %u: %02x %02x %02x %02x %02x %02x %02x %02x\\n\",\n"
 "            roster[k].name,roster[k].donor_id,psx_mod_read_byte(from+4),psx_mod_read_byte(from+5),psx_mod_read_byte(from+6),\n"
 "            psx_mod_read_byte(from+7),psx_mod_read_byte(from+8),psx_mod_read_byte(from+9),psx_mod_read_byte(from+10),psx_mod_read_byte(from+11));\n", 1),
# T3CB-PATCH-17: a custom fighter's music can come from another fighter than its stage.
("            psx_mod_write_byte(d+11,psx_mod_read_byte(owner+11));\n",
 "            /* T3CB-PATCH-17: a custom fighter's own choice of music */\n"
 "            uint32_t tune=roster[k].custom?psx_mod_read_word(0x80097d40+roster[k].music_owner*16):owner;\n"
 "            psx_mod_write_byte(d+11,psx_mod_read_byte(tune+11));\n", 1),
("            arena_value=psx_mod_read_byte(record+10);music_value=psx_mod_read_byte(record+11);\n",
 "            arena_value=psx_mod_read_byte(record+10);music_value=psx_mod_read_byte(record+11);\n"
 "            /* T3CB-PATCH-17: a custom fighter's own choice of music */\n"
 "            if(roster[k].custom && roster[k].music_owner<STOCK_FIGHTERS)\n"
 "                music_value=psx_mod_read_byte(psx_mod_read_word(0x80097d40+roster[k].music_owner*16)+11);\n", 1),
# The strong-hit effect: a custom fighter has its donor's pack, so its donor's header.
("        if(tekken3_guest_character((ptr-EFFECT_HEADERS)/EFFECT_HEADER)>=0)psx_mod_write_word(at,jin);",
 "        unsigned id=(ptr-EFFECT_HEADERS)/EFFECT_HEADER;int donor=tekken3_guest_native(id);\n"
 "        if(tekken3_guest_character(id)>=0)psx_mod_write_word(at,donor>=0?EFFECT_HEADERS+(unsigned)donor*EFFECT_HEADER:jin);", 1),
# --- T3CB-PATCH-3 diagnostics: where a custom fighter's moves come from ---
("    __real_func_80052958(cpu);\n}",
 "    remap_probe(0x80052958u,cpu);\n    __real_func_80052958(cpu);\n}", 1),
("    __real_func_80052990(cpu);\n}",
 "    remap_probe(0x80052990u,cpu);\n    __real_func_80052990(cpu);\n}", 1),
("void tekken3_ttt1_roster_tick(void) {\n",
 "/* T3CB-PATCH-3: diagnostics for the custom fighters' moves. */\n"
 "static void remap_probe(uint32_t at,CPUState *cpu) {\n"
 "    static unsigned calls;\n"
 "    if(calls<24 && (cpu->pc==0 || cpu->pc==at)){calls++;fprintf(stderr,\"Custom probe: %08x a0=%08x a1=%u ra=%08x\\n\",at,cpu->gpr[4],cpu->gpr[5],cpu->gpr[31]);}\n"
 "}\n"
 "static void custom_fight_probe(void) {\n"
 "    static uint32_t seen[2];\n"
 "    for(unsigned p=0;p<2;p++) {\n"
 "        unsigned id=psx_mod_read_half(0x800a9240+p*0x188c);\n"
 "        if(tekken3_guest_native(id)<0)continue;\n"
 "        uint32_t base=psx_mod_read_word(0x800adc20+p*4);\n"
 "        unsigned key=base>=0x80010000 && base<=0x801f0000?psx_mod_read_word(base)&0xffff:0xffff;\n"
 "        uint32_t actor=0x800a9228+p*0x188c;\n"
 "        unsigned move_id=psx_mod_read_half(actor+0x16),model=psx_mod_read_half(actor+28);\n"
 "        uint32_t sig=base^key<<20^id^move_id<<8^model<<14;\n"
 "        if(sig==seen[p])continue;seen[p]=sig;\n"
 "        unsigned sel=psx_mod_read_half(0x800add98+p*2)&3;\n"
 "        fprintf(stderr,\"Custom probe: P%u character %u, moves at %08x, header %04x (key %u), model map %u, actor+0x16 %u, actor+28 model %u\\n\",\n"
 "            p+1,id,base,key,key>>8,psx_mod_read_byte(model_map+id*4+sel),move_id,model);\n"
 "    }\n"
 "}\n"
 "/* T3CB-PATCH-5: Mokujin's round-start draw for custom fighters based on him. Stock\n"
 " * T3 only draws when actor+0x18 == 15 (0x8002AA44), so do the same draw here:\n"
 " * an unlocked fighter (0x80097EF0 & 0x13FFF) whose ID goes to actor+0x16. */\n"
 "void tekken3_custom_copycat_draw(void) {\n"
 "    unsigned mask=psx_mod_read_word(0x80097ef0)&0x13fff,ids[22],n=0;\n"
 "    for(unsigned i=0;i<22;i++)if(mask>>i&1)ids[n++]=i;\n"
 "    for(unsigned p=0;p<2 && n;p++) {\n"
 "        uint32_t actor=0x800a9228+p*0x188c;\n"
 "        int k=tekken3_guest_character(psx_mod_read_half(actor+0x18));\n"
 "        if(k<0 || !roster[k].custom || roster[k].donor_id!=15)continue;\n"
 "        unsigned id=ids[draw(n)];\n"
 "        unsigned drawn=psx_mod_read_byte(psx_mod_read_word(0x80097d40+id*16)+9);\n"
 "        psx_mod_write_half(actor+0x16,(uint16_t)drawn);\n"
 "        fprintf(stderr,\"Custom fighters: %s copies character %u this round\\n\",roster[k].name,drawn);\n"
 "    }\n"
 "}\n"
 "/* T3CB-PATCH-6: Mokujin's sword. 0x8003615C sets actor+0x7C0 = (actor+0x16 == 4) only\n"
 " * when actor+0x18 == 15, so Mokujin holds it with Yoshimitsu's moves only. */\n"
 "static void copycat_sword(void) {\n"
 "    for(unsigned p=0;p<2;p++) {\n"
 "        uint32_t actor=0x800a9228+p*0x188c;\n"
 "        if(tekken3_guest_native(psx_mod_read_half(actor+0x18))==15)\n"
 "            psx_mod_write_word(actor+0x7c0,psx_mod_read_half(actor+0x16)==4);\n"
 "    }\n"
 "}\n"
 "/* T3CB-PATCH-8: 0x8007619C(player, actor+0x18, data), called by the fighter loader\n"
 " * (0x800365A8), uploads table[ID].count tiles from the 6-byte table at 0x80027950,\n"
 " * which has 22 rows. Custom IDs read past it: ID 43 found 256 and wiped both fighter\n"
 " * bands and the CLUT rows. The routine reads a copy whose custom rows hold their\n"
 " * donor's row; every other row is copied live, so nothing else changes. */\n"
 "static void custom_strips(void) {\n"
 "    static uint32_t table;\n"
 "    if(!table && !(table=psx_mod_alloc_guest_memory(64*6,16)))return;\n"
 "    for(unsigned id=0;id<64;id++) {\n"
 "        int d=tekken3_guest_native(id),k=tekken3_guest_character(id);\n"
 "        unsigned row=d>=0?(unsigned)d:k>=0 && (unsigned)k>=tag_count?roster[k].donor_id:id;   /* T3CB-PATCH-23: a guest-style fighter reads its guest's row */\n"
 "        copy_guest(table+id*6,0x80027950+row*6,6);\n"
 "    }\n"
 "    patch(0x800761b4,0x3c038002,0x3c030000|(table>>16));\n"
 "    patch(0x800761b8,0x24637950,0x34630000|(table&65535));\n"
 "}\n"
 "/* T3CB-PATCH-9: colour variants. <prefix>-pal.bin, written by the builder: \"T3CP\", u16 version,\n"
 " * u16 entries; each u8 slot, u8 base costume, u16 CLUT id, u16 count, then count PS1 colours.\n"
 " * A variant sits on a costume slot the donor leaves free (model map 255 there). */\n"
 "static unsigned char *custom_pal[CUSTOM_MAX];\n"
 "static unsigned custom_pal_size[CUSTOM_MAX],custom_pal_tried[CUSTOM_MAX];\n"
 "static unsigned pal16(const unsigned char *p){return p[0]|p[1]<<8;}\n"
 "static const unsigned char *custom_palettes(unsigned k,unsigned *size) {\n"
 "    *size=0;\n"
 "    if(k<tag_count || k-tag_count>=CUSTOM_MAX || !roster[k].custom)return NULL;\n"
 "    unsigned c=k-tag_count;\n"
 "    if(!custom_pal_tried[c]) {\n"
 "        custom_pal_tried[c]=1;\n"
 "        const char *root=tekken3_ttt1_asset_root();char path[4096];\n"
 "        FILE *f=root && snprintf(path,sizeof path,\"%s/%s-pal.bin\",root,roster[k].prefix)<(int)sizeof path?fopen(path,\"rb\"):NULL;\n"
 "        if(f) {\n"
 "            fseek(f,0,SEEK_END);long n=ftell(f);fseek(f,0,SEEK_SET);\n"
 "            unsigned char *b=n>=8 && n<(1<<20)?malloc((size_t)n):NULL;\n"
 "            if(b && fread(b,1,(size_t)n,f)==(size_t)n && !memcmp(b,\"T3CP\",4) && pal16(b+4)==1) {\n"
 "                unsigned at=8,count=pal16(b+6),ok=1;\n"
 "                for(unsigned i=0;i<count && ok;i++){if(at+6>(unsigned)n){ok=0;break;}at+=6+2*pal16(b+at+4);if(at>(unsigned)n)ok=0;}\n"
 "                if(ok){custom_pal[c]=b;custom_pal_size[c]=(unsigned)n;b=NULL;\n"
 "                    fprintf(stderr,\"Custom fighters: %s has %u variant palettes\\n\",roster[k].name,count);}\n"
 "                else fprintf(stderr,\"Custom fighters: %s-pal.bin is damaged, ignored\\n\",roster[k].prefix);\n"
 "            }\n"
 "            free(b);fclose(f);\n"
 "        }\n"
 "    }\n"
 "    *size=custom_pal_size[c];return custom_pal[c];\n"
 "}\n"
 "/* T3CB-PATCH-19: a stage colour variant. <prefix>-stage.bin, written by the builder: \"T3ST\",\n"
 " * u16 version 1, u16 arena, u16 runs; per run u16 x, u16 y, u16 count, count original colours,\n"
 " * count new colours: the arena's own CLUT rows (disc record 36 + arena) recoloured. In a fight\n"
 " * on that arena with the fighter in it, a row still holding the original colours gets the new\n"
 " * ones, every frame (the game reloads some); a row something else wrote over is left alone. */\n"
 "static unsigned char *custom_stg[CUSTOM_MAX];\n"
 "static unsigned custom_stg_tried[CUSTOM_MAX];\n"
 "static const unsigned char *custom_stage(unsigned k) {\n"
 "    if(k<tag_count || k-tag_count>=CUSTOM_MAX || !roster[k].custom)return NULL;\n"
 "    unsigned c=k-tag_count;\n"
 "    if(!custom_stg_tried[c]) {\n"
 "        custom_stg_tried[c]=1;\n"
 "        const char *root=tekken3_ttt1_asset_root();char path[4096];\n"
 "        FILE *f=root && snprintf(path,sizeof path,\"%s/%s-stage.bin\",root,roster[k].prefix)<(int)sizeof path?fopen(path,\"rb\"):NULL;\n"
 "        if(f) {\n"
 "            fseek(f,0,SEEK_END);long n=ftell(f);fseek(f,0,SEEK_SET);\n"
 "            unsigned char *b=n>=10 && n<(1<<20)?malloc((size_t)n):NULL;\n"
 "            if(b && fread(b,1,(size_t)n,f)==(size_t)n && !memcmp(b,\"T3ST\",4) && pal16(b+4)==1) {\n"
 "                unsigned at=10,runs=pal16(b+8),ok=1;\n"
 "                for(unsigned i=0;i<runs && ok;i++) {\n"
 "                    if(at+6>(unsigned)n){ok=0;break;}\n"
 "                    unsigned x=pal16(b+at),y=pal16(b+at+2),cnt=pal16(b+at+4);\n"
 "                    ok=cnt>0 && cnt<=256 && x+cnt<=1024 && y<512;at+=6+4*cnt;if(at>(unsigned)n)ok=0;\n"
 "                }\n"
 "                if(ok && at==(unsigned)n){custom_stg[c]=b;b=NULL;\n"
 "                    fprintf(stderr,\"Custom fighters: %s has a stage colour variant (arena %u, %u CLUT rows)\\n\",roster[k].name,pal16(custom_stg[c]+6),runs);}\n"
 "                else fprintf(stderr,\"Custom fighters: %s-stage.bin is damaged, ignored\\n\",roster[k].prefix);\n"
 "            }\n"
 "            free(b);fclose(f);\n"
 "        }\n"
 "    }\n"
 "    return custom_stg[c];\n"
 "}\n"
 "static void custom_stage_tick(void) {\n"
 "    if(psx_mod_read_word(0x800ae204)!=8)return;\n"
 "    unsigned arena=psx_mod_read_half(0x800adc84);\n"
 "    for(unsigned p=0;p<2;p++) {\n"
 "        int k=tekken3_guest_character(psx_mod_read_half(0x800a9240+p*0x188c));\n"
 "        const unsigned char *b=k<0?NULL:custom_stage((unsigned)k);\n"
 "        if(!b || pal16(b+6)!=arena)continue;\n"
 "        unsigned at=10,runs=pal16(b+8),put=0;\n"
 "        uint16_t now[256];\n"
 "        for(unsigned i=0;i<runs;i++) {\n"
 "            unsigned x=pal16(b+at),y=pal16(b+at+2),cnt=pal16(b+at+4);\n"
 "            const unsigned char *orig=b+at+6,*want=orig+2*cnt;\n"
 "            gr_vram_transfer_out((int)x,(int)y,(int)cnt,1,now);\n"
 "            if(!memcmp(now,orig,2*cnt)){gr_vram_transfer_in((int)x,(int)y,(int)cnt,1,(const uint16_t*)want);put++;}\n"
 "            at+=6+4*cnt;\n"
 "        }\n"
 "        static unsigned logged;\n"
 "        if(put && logged<3){logged++;fprintf(stderr,\"Custom fighters: %s stage colours on arena %u (%u of %u CLUT rows)\\n\",roster[k].name,arena,put,runs);}\n"
 "        return;\n"
 "    }\n"
 "}\n"
 "/* T3CB-PATCH-20: changed move damage. <prefix>-moves.bin, written by the builder: \"T3MV\",\n"
 " * u16 version 1, u16 moveset key, u16 changes; per change u16 record, u16 original damage,\n"
 " * u16 new damage (the low byte of the record's word 5, its high byte holds flags; word 5 sets\n"
 " * the damage, tested in Practice's attack data). In a fight, while the custom fighter's player\n"
 " * holds a moveset of that key that the other player does not share (a mirror match shares\n"
 " * one), a record still holding the original damage gets the new one. When the buffer holds\n"
 " * someone else later, the changed records go back, so no other fighter gets the change. */\n"
 "/* T3CB-PATCH-21: moves on other buttons. Version 2 adds u16 swaps; per swap u16 alias slot,\n"
 " * u16 original record, u16 new record. A basic input starts the record its alias slot points\n"
 " * at (header +12, tested in Practice), so a slot still pointing at the original record points\n"
 " * at the new one, under the same rules as the damage, and goes back the same way. */\n"
 "static unsigned char *custom_mv[CUSTOM_MAX];\n"
 "static unsigned custom_mv_tried[CUSTOM_MAX];\n"
 "static uint32_t moves_header[2];\n"
 "static const unsigned char *moves_file[2];\n"
 "static unsigned moves_swaps(const unsigned char *b){return pal16(b+4)==2?pal16(b+10+6*pal16(b+8)):0;}\n"
 "static int moves_size(const unsigned char *b,long n) {\n"
 "    long at=10+6*(long)pal16(b+8);\n"
 "    if(pal16(b+4)==1)return n==at;\n"
 "    return pal16(b+4)==2 && n>=at+2 && n==at+2+6*(long)pal16(b+at);\n"
 "}\n"
 "static const unsigned char *custom_moves(unsigned k) {\n"
 "    if(k<tag_count || k-tag_count>=CUSTOM_MAX || !roster[k].custom)return NULL;\n"
 "    unsigned c=k-tag_count;\n"
 "    if(!custom_mv_tried[c]) {\n"
 "        custom_mv_tried[c]=1;\n"
 "        const char *root=tekken3_ttt1_asset_root();char path[4096];\n"
 "        FILE *f=root && snprintf(path,sizeof path,\"%s/%s-moves.bin\",root,roster[k].prefix)<(int)sizeof path?fopen(path,\"rb\"):NULL;\n"
 "        if(f) {\n"
 "            fseek(f,0,SEEK_END);long n=ftell(f);fseek(f,0,SEEK_SET);\n"
 "            unsigned char *b=n>=10 && n<(1<<16)?malloc((size_t)n):NULL;\n"
 "            if(b && fread(b,1,(size_t)n,f)==(size_t)n && !memcmp(b,\"T3MV\",4) && moves_size(b,n)) {\n"
 "                custom_mv[c]=b;b=NULL;\n"
 "                fprintf(stderr,\"Custom fighters: %s has %u changed moves, %u moved (moveset %u)\\n\",roster[k].name,pal16(custom_mv[c]+8),moves_swaps(custom_mv[c]),pal16(custom_mv[c]+6));\n"
 "            } else if(b)fprintf(stderr,\"Custom fighters: %s-moves.bin is damaged, ignored\\n\",roster[k].prefix);\n"
 "            free(b);fclose(f);\n"
 "        }\n"
 "    }\n"
 "    return custom_mv[c];\n"
 "}\n"
 "/* Puts the changes in (forward) or takes them out of a loaded moveset; returns how many. */\n"
 "static unsigned moves_put(uint32_t header,const unsigned char *b,int forward) {\n"
 "    if(header<0x80010000u || header>=0x80200000u || (psx_mod_read_word(header)>>8&255)!=pal16(b+6))return 0;\n"
 "    uint32_t records=psx_mod_read_word(header+8),alias=psx_mod_read_word(header+12);\n"
 "    if(records<0x80010000u || alias<=records || alias>=0x80200000u)return 0;\n"
 "    unsigned count=(alias-records)/56,put=0;\n"
 "    for(unsigned i=0,n=pal16(b+8);i<n;i++) {\n"
 "        unsigned r=pal16(b+10+6*i),from=pal16(b+12+6*i)&255,to=pal16(b+14+6*i)&255;\n"
 "        if(!forward){unsigned t=from;from=to;to=t;}\n"
 "        if(r>=count || from==to)continue;\n"
 "        uint32_t at=records+56*r+20;unsigned v=psx_mod_read_half(at);\n"
 "        if((v&255)==from){psx_mod_write_half(at,(uint16_t)((v&0xff00)|to));put++;}\n"
 "    }\n"
 "    const unsigned char *s=b+12+6*pal16(b+8);\n"
 "    for(unsigned i=0,n=moves_swaps(b);i<n;i++) {           /* T3CB-PATCH-21 */\n"
 "        unsigned slot=pal16(s+6*i),from=pal16(s+2+6*i),to=pal16(s+4+6*i);\n"
 "        if(!forward){unsigned t=from;from=to;to=t;}\n"
 "        uint32_t at=alias+4*slot;\n"
 "        if(from>=count || to>=count || from==to || at+4>=0x80200000u)continue;\n"
 "        if(psx_mod_read_word(at)==records+56*from){psx_mod_write_word(at,records+56*to);put++;}\n"
 "    }\n"
 "    return put;\n"
 "}\n"
 "static void custom_moves_tick(void) {\n"
 "    if(psx_mod_read_word(0x800ae204)!=8)return;\n"
 "    uint32_t headers[2]={psx_mod_read_word(0x800adc20),psx_mod_read_word(0x800adc24)};\n"
 "    for(unsigned p=0;p<2;p++) {\n"
 "        int k=tekken3_guest_character(psx_mod_read_half(0x800a9240+p*0x188c));\n"
 "        const unsigned char *b=k<0?NULL:custom_moves((unsigned)k);\n"
 "        int mine=b && headers[p]!=headers[1-p];\n"
 "        if(moves_file[p] && (!mine || moves_header[p]!=headers[p] || moves_file[p]!=b)) {\n"
 "            moves_put(moves_header[p],moves_file[p],0);   /* someone else's now: back */\n"
 "            moves_file[p]=NULL;moves_header[p]=0;\n"
 "        }\n"
 "        if(!mine)continue;\n"
 "        unsigned put=moves_put(headers[p],b,1);\n"
 "        moves_header[p]=headers[p];moves_file[p]=b;\n"
 "        static unsigned logged;\n"
 "        if(put && logged<4){logged++;fprintf(stderr,\"Custom fighters: P%u %s changed moves in (%u)\\n\",p+1,roster[k].name,put);}\n"
 "    }\n"
 "}\n"
 "/* T3CB-PATCH-22: the COMMAND LIST of a fighter with moves on other buttons. <prefix>-commands.bin,\n"
 " * written by the builder: \"T3CL\", u16 version 1, u16 pairs; per pair u16 size of the original,\n"
 " * u16 size of the new list, the original list, the new one. A fight copies the style's list to\n"
 " * 0x800A3628 + 0x1A0 * player (tested: byte for byte the disc's); the custom fighter's buffer\n"
 " * still holding an original gets the new list (shown by the pause menu's COMMAND LIST). */\n"
 "static unsigned char *custom_cl[CUSTOM_MAX];\n"
 "static unsigned custom_cl_tried[CUSTOM_MAX];\n"
 "static const unsigned char *custom_commands(unsigned k) {\n"
 "    if(k<tag_count || k-tag_count>=CUSTOM_MAX || !roster[k].custom)return NULL;\n"
 "    unsigned c=k-tag_count;\n"
 "    if(!custom_cl_tried[c]) {\n"
 "        custom_cl_tried[c]=1;\n"
 "        const char *root=tekken3_ttt1_asset_root();char path[4096];\n"
 "        FILE *f=root && snprintf(path,sizeof path,\"%s/%s-commands.bin\",root,roster[k].prefix)<(int)sizeof path?fopen(path,\"rb\"):NULL;\n"
 "        if(f) {\n"
 "            fseek(f,0,SEEK_END);long n=ftell(f);fseek(f,0,SEEK_SET);\n"
 "            unsigned char *b=n>=8 && n<(1<<16)?malloc((size_t)n):NULL;\n"
 "            int ok=b && fread(b,1,(size_t)n,f)==(size_t)n && !memcmp(b,\"T3CL\",4) && pal16(b+4)==1;\n"
 "            long at=8;\n"
 "            for(unsigned i=0;ok && i<pal16(b+6);i++) {\n"
 "                if(at+4>n){ok=0;break;}\n"
 "                unsigned so=pal16(b+at),sn=pal16(b+at+2);\n"
 "                if(!so || so>0x1a0 || !sn || sn>0x1a0){ok=0;break;}\n"
 "                at+=4+so+sn;\n"
 "            }\n"
 "            if(ok && at==n){custom_cl[c]=b;b=NULL;fprintf(stderr,\"Custom fighters: %s has its own COMMAND LIST\\n\",roster[k].name);}\n"
 "            else if(b)fprintf(stderr,\"Custom fighters: %s-commands.bin is damaged, ignored\\n\",roster[k].prefix);\n"
 "            free(b);fclose(f);\n"
 "        }\n"
 "    }\n"
 "    return custom_cl[c];\n"
 "}\n"
 "/* T3CB-PATCH-22: a custom fighter's CPU personality. <prefix>-cpu.txt, written by the builder:\n"
 " * a block (0-29) of the CPU behaviour table at 0x800231AC (3 difficulties x 10 stages, 110\n"
 " * bytes). The game copies the fight's block to the player's AI structure (0x8009F318 + 0x330\n"
 " * * player, +568; tested); while the CPU plays the custom fighter, its structure holds the\n"
 " * chosen block instead (tested: EASY stage 1 let 40 of 240 jabs in, HARD stage 10 about 6). */\n"
 "static int custom_cpu_block[CUSTOM_MAX],custom_cpu_tried[CUSTOM_MAX];\n"
 "static int custom_cpu(unsigned k) {\n"
 "    if(k<tag_count || k-tag_count>=CUSTOM_MAX || !roster[k].custom)return -1;\n"
 "    unsigned c=k-tag_count;\n"
 "    if(!custom_cpu_tried[c]) {\n"
 "        custom_cpu_tried[c]=1;custom_cpu_block[c]=-1;\n"
 "        const char *root=tekken3_ttt1_asset_root();char path[4096];int v;\n"
 "        FILE *f=root && snprintf(path,sizeof path,\"%s/%s-cpu.txt\",root,roster[k].prefix)<(int)sizeof path?fopen(path,\"r\"):NULL;\n"
 "        if(f){if(fscanf(f,\"%d\",&v)==1 && v>=0 && v<30)custom_cpu_block[c]=v;fclose(f);}\n"
 "        if(custom_cpu_block[c]>=0)fprintf(stderr,\"Custom fighters: %s has CPU block %d\\n\",roster[k].name,custom_cpu_block[c]);\n"
 "    }\n"
 "    return custom_cpu_block[c];\n"
 "}\n"
 "static void custom_cpu_tick(void) {\n"
 "    if(psx_mod_read_word(0x800ae204)!=8)return;\n"
 "    unsigned human=psx_mod_read_half(0x800ae1f8)?0:1,p=human^1;\n"
 "    int k=tekken3_guest_character(psx_mod_read_half(0x800a9240+p*0x188c));\n"
 "    int block=k<0?-1:custom_cpu((unsigned)k);\n"
 "    if(block<0)return;\n"
 "    uint32_t from=0x800231ac+(uint32_t)block*110,to=0x8009f318+p*0x330+568;\n"
 "    for(unsigned j=0;j<110;j++) {\n"
 "        unsigned v=psx_mod_read_byte(from+j);\n"
 "        if(psx_mod_read_byte(to+j)!=v)psx_mod_write_byte(to+j,(uint8_t)v);\n"
 "    }\n"
 "}\n"
 "static void custom_commands_tick(void) {\n"
 "    if(psx_mod_read_word(0x800ae204)!=8)return;\n"
 "    for(unsigned p=0;p<2;p++) {\n"
 "        int k=tekken3_guest_character(psx_mod_read_half(0x800a9240+p*0x188c));\n"
 "        const unsigned char *b=k<0?NULL:custom_commands((unsigned)k);\n"
 "        if(!b)continue;\n"
 "        uint32_t buf=0x800a3628+p*0x1a0;\n"
 "        const unsigned char *e=b+8;\n"
 "        for(unsigned i=0;i<pal16(b+6);i++) {\n"
 "            unsigned so=pal16(e),sn=pal16(e+2),same=1;\n"
 "            for(unsigned j=0;j<so && same;j++)same=psx_mod_read_byte(buf+j)==e[4+j];\n"
 "            if(same) {\n"
 "                for(unsigned j=0;j<sn;j++)psx_mod_write_byte(buf+j,e[4+so+j]);\n"
 "                fprintf(stderr,\"Custom fighters: P%u %s COMMAND LIST in\\n\",p+1,roster[k].name);\n"
 "                break;\n"
 "            }\n"
 "            e+=4+so+sn;\n"
 "        }\n"
 "    }\n"
 "}\n"
 "/* The model of a custom fighter's costume slot c: the donor's, else the base model of the\n"
 " * colour variant placed on that free slot, else none (255). */\n"
 "static unsigned custom_slot_model(unsigned k,unsigned c) {\n"
 "    unsigned donor=roster[k].donor_id,own=psx_mod_read_byte(0x800958c4+donor*4+c),size;\n"
 "    const unsigned char *b=custom_palettes(k,&size);\n"
 "    if(own!=255 || !b)return own;\n"
 "    for(unsigned i=0,at=8,count=pal16(b+6);i<count;i++,at+=6+2*pal16(b+at+4))\n"
 "        if(b[at]==c)return psx_mod_read_byte(0x800958c4+donor*4+(b[at+1]&3));\n"
 "    return 255;\n"
 "}\n"
 "/* In a fight, a custom fighter in a variant's slot gets that variant's palettes, in its\n"
 " * player's CLUT rows (504 + player * 4 + row), every frame so nothing reloads them away. */\n"
 "static void custom_palette_tick(void) {\n"
 "    if(psx_mod_read_word(0x800ae204)!=8)return;\n"
 "    for(unsigned p=0;p<2;p++) {\n"
 "        uint32_t actor=0x800a9228+p*0x188c;\n"
 "        int k=tekken3_guest_character(psx_mod_read_half(actor+0x18));\n"
 "        unsigned size;const unsigned char *b=k>=0?custom_palettes((unsigned)k,&size):NULL;\n"
 "        if(!b)continue;\n"
 "        unsigned slot=psx_mod_read_half(actor+0x14)&3;\n"
 "        for(unsigned i=0,at=8,count=pal16(b+6);i<count;i++,at+=6+2*pal16(b+at+4)) {\n"
 "            unsigned id=pal16(b+at+2),n=pal16(b+at+4);\n"
 "            if(b[at]!=slot || (n!=16 && n!=256) || (id>>6)>3)continue;\n"
 "            gr_vram_transfer_in((int)((id&63)*16),(int)(504+p*4+(id>>6)),(int)n,1,(const uint16_t*)(b+at+6));\n"
 "        }\n"
 "    }\n"
 "}\n"
 "/* T3CB-PATCH-10: own models. <prefix>-model.bin, written by the builder: \"T3CM\", u16 version 1,\n"
 " * u16 model it replaces, u32 model bytes, u32 relocations, the replaced model's stock header\n"
 " * (24 + 27 * 56 bytes, pointers as file offsets), the new 3DMK model, then u32 offsets of its\n"
 " * pointer words. Just before the game initializes a fighter, a loaded model whose header is\n"
 " * that stock header, relocated, is overwritten with the new model, its pointers relocated. */\n"
 "#define CM_HEADER (24+27*56)\n"
 "int tekken3_ttt1_roster_enabled(void);\n"
 "static unsigned char *custom_mdl[CUSTOM_MAX];\n"
 "static unsigned custom_mdl_tried[CUSTOM_MAX];\n"
 "static uint32_t custom_mdl_at[2];static int custom_mdl_k[2];static unsigned custom_mdl_checks[2];\n"
 "static uint32_t cm32(const unsigned char *p){return p[0]|p[1]<<8|p[2]<<16|(uint32_t)p[3]<<24;}\n"
 "static const unsigned char *custom_model(unsigned k) {\n"
 "    if(k<tag_count || k-tag_count>=CUSTOM_MAX || !roster[k].custom)return NULL;\n"
 "    unsigned c=k-tag_count;\n"
 "    if(!custom_mdl_tried[c]) {\n"
 "        custom_mdl_tried[c]=1;\n"
 "        const char *root=tekken3_ttt1_asset_root();char path[4096];\n"
 "        FILE *f=root && snprintf(path,sizeof path,\"%s/%s-model.bin\",root,roster[k].prefix)<(int)sizeof path?fopen(path,\"rb\"):NULL;\n"
 "        if(f) {\n"
 "            fseek(f,0,SEEK_END);long n=ftell(f);fseek(f,0,SEEK_SET);\n"
 "            unsigned char *b=n>16+CM_HEADER && n<(1<<20)?malloc((size_t)n):NULL;\n"
 "            int ok=b && fread(b,1,(size_t)n,f)==(size_t)n && !memcmp(b,\"T3CM\",4) && (pal16(b+4)==1 || pal16(b+4)==2);\n"
 "            if(ok) {\n"
 "                uint32_t size=cm32(b+8),count=cm32(b+12),end=16u+CM_HEADER+size+4u*count;\n"
 "                if(pal16(b+4)==2) {                      /* T3CB-PATCH-11: + \"T3TX\" texture */\n"
 "                    ok=end+12<=(uint32_t)n && !memcmp(b+end,\"T3TX\",4);\n"
 "                    if(ok){unsigned w=pal16(b+end+4),h=pal16(b+end+6),id=pal16(b+end+8),c=pal16(b+end+10);\n"
 "                        /* T3CB-PATCH-12: id 0xFFFF = c CLUT runs follow, each u16 id, u16 count, colours */\n"
 "                        unsigned runs=id==0xFFFF?c:1;uint32_t at=end+12;\n"
 "                        ok=w>0 && w<=64 && h>0 && h<=256 && runs>0 && runs<=8;\n"
 "                        for(unsigned r=0;ok && r<runs;r++){\n"
 "                            unsigned rid=id==0xFFFF?pal16(b+at):id,rc=id==0xFFFF?pal16(b+at+2):c;\n"
 "                            if(id==0xFFFF)at+=4;\n"
 "                            ok=at<=(uint32_t)n && rc>0 && rc<=256 && (rid&63)*16+rc<=1024 && (rid>>6)<4;at+=2*rc;}\n"
 "                        end=at+2*w*h;}\n"
 "                }\n"
 "                ok=ok && size>=CM_HEADER && size%4==0 && count<65536 && end==(uint32_t)n;\n"
 "                for(uint32_t i=0;ok && i<count;i++){uint32_t r=cm32(b+16+CM_HEADER+size+4*i);ok=r%4==0 && r+4<=size;}\n"
 "            }\n"
 "            if(ok){custom_mdl[c]=b;b=NULL;fprintf(stderr,\"Custom fighters: %s has its own model (%u bytes over model %u)\\n\",\n"
 "                roster[k].name,cm32(custom_mdl[c]+8),pal16(custom_mdl[c]+6));}\n"
 "            else fprintf(stderr,\"Custom fighters: %s-model.bin is damaged, ignored\\n\",roster[k].prefix);\n"
 "            free(b);fclose(f);\n"
 "        }\n"
 "    }\n"
 "    return custom_mdl[c];\n"
 "}\n"
 "/* Called by tekken3_ttt1_before_init with the model the game is about to initialize. */\n"
 "void tekken3_custom_model_install(uint32_t model) {\n"
 "    if(!tekken3_ttt1_roster_enabled() || model<0x80000000u || model>=0x80200000u)return;\n"
 "    for(unsigned p=0;p<2;p++) {\n"
 "        int k=tekken3_guest_character(psx_mod_read_half(0x800a9228+p*0x188c+0x18));\n"
 "        const unsigned char *b=k>=0?custom_model((unsigned)k):NULL;\n"
 "        if(!b)continue;\n"
 "        uint32_t mine=psx_mod_read_word(0x8009bd28+p*4);\n"
 "        const unsigned char *stock=b+16,*file=stock+CM_HEADER;\n"
 "        uint32_t size=cm32(b+8),count=cm32(b+12),replaced=pal16(b+6);\n"
 "        const unsigned char *rel=file+size;\n"
 "        int same=1;                                      /* is this the stock model, relocated? */\n"
 "        for(unsigned r=0;r<27 && same;r++)for(unsigned w=0;w<14 && same;w++) {\n"
 "            uint32_t want=cm32(stock+24+r*56+w*4),got=psx_mod_read_word(model+24+r*56+w*4);\n"
 "            int ptr=(w<3 || w==12 || w==13) && want>2;\n"
 "            same=got==(ptr?model+want:want);\n"
 "        }\n"
 "        if(!same)continue;\n"
 "        if(mine && mine!=model) {                        /* the other player's copy of it */\n"
 "            static uint32_t said[2];                     /* once per address, not every init */\n"
 "            if(said[p]!=model){said[p]=model;\n"
 "                fprintf(stderr,\"Custom fighters: model %u at %08X is not P%u's (%08X)\\n\",replaced,model,p+1,mine);}\n"
 "            continue;\n"
 "        }\n"
 "        uint32_t room=psx_mod_read_word(0x80095a9c+replaced*12);\n"
 "        if(size>room) {\n"
 "            fprintf(stderr,\"Custom fighters: %s's own model needs %u bytes, model %u has %u; not used\\n\",\n"
 "                    roster[k].name,size,replaced,room);\n"
 "            continue;\n"
 "        }\n"
 "        unsigned header_ok=psx_mod_read_word(model+16)==model+cm32(stock+16);\n"
 "        for(uint32_t i=0;i<size;i+=4)psx_mod_write_word(model+i,cm32(file+i));\n"
 "        for(uint32_t i=0;i<count;i++){uint32_t r=cm32(rel+4*i);psx_mod_write_word(model+r,cm32(file+r)+model);}\n"
 "        if(custom_mdl_at[p]!=model)\n"
 "            fprintf(stderr,\"Custom fighters: %s own model installed at %08X (P%u%s, %u bytes, %u relocations, header +16 %s)\\n\",\n"
 "                    roster[k].name,model,p+1,mine?\"\":\", player by elimination\",size,count,header_ok?\"relocated\":\"NOT relocated\");\n"
 "        custom_mdl_at[p]=model;custom_mdl_k[p]=k;custom_mdl_checks[p]=0;\n"
 "        return;\n"
 "    }\n"
 "}\n"
 "/* T3CB-PATCH-10 diagnostic: during the fight, is the installed model still in memory, and is\n"
 " * it the one the player draws (0x8009BD28)? Logged a few times per installation.\n"
 " * T3CB-PATCH-11: an own model with a texture (version 2) gets it in the first texture page of\n"
 " * its player's band (VRAM x 384, y player * 256), its CLUT in the player's CLUT rows; the CLUT\n"
 " * every frame (after the palette variants), the texels too. Only while the player\n"
 " * still draws the installed model. */\n"
 "static void custom_model_check(void) {\n"
 "    static unsigned frame;\n"
 "    if(psx_mod_read_word(0x800ae204)!=8)return;\n"
 "    /* T3CB-PATCH-18: not on Team Battle's FIGHT screen (state 8 before phase 6): the fighters\n"
 "     * are not drawn yet, and the team's tiles and palettes are up in the same VRAM */\n"
 "    if(psx_mod_read_word(0x800afa88)==2 && psx_mod_read_half(0x800ae224)<6)return;\n"
 "    frame++;\n"
 "    for(unsigned p=0;p<2;p++) {\n"
 "        if(!custom_mdl_at[p])continue;\n"
 "        uint32_t actor=0x800a9228+p*0x188c;\n"
 "        if(tekken3_guest_character(psx_mod_read_half(actor+0x18))!=custom_mdl_k[p]\n"
 "           || psx_mod_read_word(0x8009bd28+p*4)!=custom_mdl_at[p])continue;\n"
 "        const unsigned char *b=custom_model((unsigned)custom_mdl_k[p]);\n"
 "        if(!b)continue;\n"
 "        uint32_t model=custom_mdl_at[p],size=cm32(b+8),count=cm32(b+12);\n"
 "        if(pal16(b+4)==2) {\n"
 "            const unsigned char *t=b+16+CM_HEADER+size+4*count;\n"
 "            unsigned w=pal16(t+4),h=pal16(t+6),id=pal16(t+8),c=pal16(t+10),runs=id==0xFFFF?c:1,colours=0;\n"
 "            const unsigned char *at=t+12;\n"
 "            for(unsigned r=0;r<runs;r++) {                  /* T3CB-PATCH-12: several CLUT runs (T3CB-PATCH-13: renderer probe options) */\n"
 "                unsigned rid=id==0xFFFF?pal16(at):id,rc=id==0xFFFF?pal16(at+2):c;\n"
 "                if(id==0xFFFF)at+=4;\n"
 "                gr_vram_transfer_in((int)((rid&63)*16),(int)(504+p*4+(rid>>6)),(int)rc,1,(const uint16_t*)at);\n"
 "                at+=2*rc;colours+=rc;\n"
 "            }\n"
 "            /* T3CB-PATCH-14: the texels every frame too: the game reloads the donor's face\n"
 "             * texture (VRAM 384,64) during the fight, which showed through for up to a second */\n"
 "            gr_vram_transfer_in(384,(int)(p*256),(int)w,(int)h,(const uint16_t*)at);\n"
 "            if(custom_mdl_checks[p]==0)fprintf(stderr,\"Custom fighters: P%u own texture uploaded (%ux%u halfwords, %u colours in %u CLUT runs)\\n\",p+1,w,h,colours,runs);\n"
 "        }\n"
 "        if(custom_mdl_checks[p]==0)custom_mdl_checks[p]=1;\n"
 "        if(frame%120 || custom_mdl_checks[p]>4)continue;\n"
 "        custom_mdl_checks[p]++;\n"
 "        uint32_t differ=0,first=0;\n"
 "        const unsigned char *file=b+16+CM_HEADER;\n"
 "        for(uint32_t i=CM_HEADER;i<size;i+=4)if(psx_mod_read_word(model+i)!=cm32(file+i)){if(!differ)first=i;differ++;}\n"
 "        fprintf(stderr,\"Custom fighters: P%u model check: drawn model %08X, installed %08X, %u of %u data words differ (first at +%u)\\n\",\n"
 "                p+1,psx_mod_read_word(0x8009bd28+p*4),model,differ,(size-CM_HEADER)/4,first);\n"
 "    }\n"
 "}\n"
 "void tekken3_ttt1_roster_tick(void) {\n", 1),
("    patch_tables();\n    unsigned state=psx_mod_read_word(0x800ae204);\n",
 "    patch_tables();\n    custom_fight_probe();\n    copycat_sword();\n    custom_strips();\n    custom_palette_tick();\n    custom_model_check();\n    custom_stage_tick();                    /* T3CB-PATCH-19 */\n    custom_moves_tick();                    /* T3CB-PATCH-20 */\n    custom_commands_tick();                 /* T3CB-PATCH-22 */\n    custom_cpu_tick();\n    unsigned state=psx_mod_read_word(0x800ae204);\n", 1),
# --- T3CB-PATCH-4: a custom fighter's move key (actor+0x16) is its donor's, not GUEST_ID ---
("            cpu->gpr[4]=GUEST_ID;",
 "            cpu->gpr[4]=guest_move_key((uint16_t)cpu->gpr[4]);", 1),
("            cpu->gpr[2]=GUEST_ID;cpu->pc=cpu->gpr[31];return;",
 "            cpu->gpr[2]=guest_move_key((uint16_t)cpu->gpr[2]);cpu->pc=cpu->gpr[31];return;", 1),
("void __wrap_func_8002D1DC(CPUState *cpu) {\n",
 "/* T3CB-PATCH-4: the moveset loader (0x80069F74) reads actor+0x16, so a custom\n"
 " * fighter keeps its donor's moveset key there; TTT1 guests keep 23.\n"
 " * T3CB-PATCH-7: the key is the donor descriptor's byte 9, as stock T3 sets it\n"
 " * (0x8004F2BC); it differs from the ID for Mokujin, Gon, Anna, Dr. B, True Ogre. */\n"
 "static unsigned guest_move_key(unsigned id){int d=tekken3_guest_native(id);\n"
 "    return d<0?GUEST_ID:psx_mod_read_byte(psx_mod_read_word(0x80097d40+(unsigned)d*16)+9);}\n"
 "void __wrap_func_8002D1DC(CPUState *cpu) {\n", 1),
# Custom fighters keep their name plate but do not switch the TTT1 side on.
("wanted=1;gr_vram_transfer_in(464,p*256,guests[p].name_halfwords,16,guests[p].name_pixels);",
 "if(tekken3_guest_native(id)<0)wanted=1;gr_vram_transfer_in(464,p*256,guests[p].name_halfwords,16,guests[p].name_pixels);", 1),
("        uint32_t profile=psx_mod_read_word(0x80096ff0+9*4);",
 "        uint32_t profile=psx_mod_read_word(0x80096ff0+guest_donor(psx_mod_read_half(cpu->gpr[4]+24))*4);", 1),
# --- VS grid pages ---
("        int shown=grid_page?i<roster_count:i<STOCK_GRID_CELLS;\n"
 "        unsigned id=grid_page?(i<roster_count?(GUEST_ID+i)*4:0x58):(i<STOCK_GRID_CELLS?team_order[i]:0x58);",
 "        int shown=grid_page?i<page_len(grid_page):i<STOCK_GRID_CELLS;\n"
 "        unsigned id=grid_page?(i<page_len(grid_page)?(GUEST_ID+page_first(grid_page)+i)*4:0x58):(i<STOCK_GRID_CELLS?team_order[i]:0x58);", 1),
("static unsigned grid_rows(void){return grid_page?(roster_count+VS_TAG_COLS-1)/VS_TAG_COLS:3;}",
 "static unsigned grid_rows(void){return grid_page?(page_len(grid_page)+VS_TAG_COLS-1)/VS_TAG_COLS:3;}", 1),
("static void grid_switch(void) {\n    grid_page=!grid_page;write_grid_page();grid_availability();",
 "static void tiles_release(void);\n"
 "static void grid_switch(int step) {\n"
 "    int previous=grid_page;\n"
 "    grid_page=(grid_page+step+page_total())%page_total();\n"
 "    write_grid_page();grid_availability();", 1),
("            grid_confirmed_page[p]=!grid_page;", "            grid_confirmed_page[p]=previous;", 1),
("            int guest=tekken3_guest_character(id)>=0;\n            if(guest==grid_page)mask&=~(1u<<(id&31));",
 "            int k=tekken3_guest_character(id),on=k<0?0:guest_page((unsigned)k);\n"
 "            if(on==grid_page)mask&=~(1u<<(id&31));", 1),
("            for(unsigned k=0;k<roster_count;k++) {\n                unsigned id=GUEST_ID+k;int chosen=0;",
 "            for(unsigned k=page_first(grid_page);k<page_first(grid_page)+page_len(grid_page);k++) {\n"
 "                unsigned id=GUEST_ID+k;int chosen=0;", 1),
("    unsigned cells=grid_page?roster_count:STOCK_GRID_CELLS,left=cells-y*grid_cols();",
 "    unsigned cells=grid_page?page_len(grid_page):STOCK_GRID_CELLS,left=cells-y*grid_cols();", 1),
("        unsigned id=grid_page && cell<roster_count?GUEST_ID+cell:0;",
 "        unsigned id=grid_page && cell<page_len(grid_page)?GUEST_ID+page_first(grid_page)+cell:0;", 1),
# --- T3CB-PATCH-18: both guest pages' tiles are in VRAM together. Custom fighters' tiles have
# their own place (a Team Battle team can mix the pages); their palettes are cut to 128 colours,
# two per palette row. ---
("static const VramArea tile_areas[2]={{TILE_X,TILE_Y,AREA_W,AREA_H},{TILE_X,EXTRA_Y,EXTRA_MAX*TILE_W,TILE_H}};\n"
 "static const VramArea palette_areas[2]={{0,TILE_PALETTE_Y,256,TAG_BASE},{0,EXTRA_PALETTE_Y,256,EXTRA_MAX}};",
 "/* T3CB-PATCH-18: custom fighters' tiles at (384,256), texture page 0x96, eight per row, and\n"
 " * their palettes, cut to 128 colours, two per row from (0,504): both measured empty at the\n"
 " * selector and Team Battle's FIGHT screen (2026-10-16), so both guest pages' tiles are up\n"
 " * together. */\n"
 "enum { CUSTOM_TILE_Y=256, CUSTOM_PAGE=0x96, CUSTOM_PALETTE_Y=504 };\n"
 "static const VramArea tile_areas[3]={{TILE_X,TILE_Y,AREA_W,AREA_H},{TILE_X,EXTRA_Y,EXTRA_MAX*TILE_W,TILE_H},\n"
 "    {TILE_X,CUSTOM_TILE_Y,AREA_W,AREA_H}};\n"
 "static const VramArea palette_areas[3]={{0,TILE_PALETTE_Y,256,TAG_BASE},{0,EXTRA_PALETTE_Y,256,EXTRA_MAX},\n"
 "    {0,CUSTOM_PALETTE_Y,256,CUSTOM_MAX/2}};", 1),
("static unsigned tile_x(unsigned k){return TILE_X+(k<TAG_BASE?k%TAG_BASE_COLS:k-TAG_BASE)*TILE_W;}\n"
 "static unsigned tile_y(unsigned k){return k<TAG_BASE?TILE_Y+(k/TAG_BASE_COLS)*TILE_H:EXTRA_Y;}\n"
 "static unsigned tile_palette_y(unsigned k){return k<TAG_BASE?TILE_PALETTE_Y+k:EXTRA_PALETTE_Y+k-TAG_BASE;}",
 "static int custom_tile(unsigned k){return k>=tag_count;}\n"
 "static unsigned tile_x(unsigned k){\n"
 "    if(custom_tile(k))return TILE_X+(k-tag_count)%TAG_BASE_COLS*TILE_W;\n"
 "    return TILE_X+(k<TAG_BASE?k%TAG_BASE_COLS:k-TAG_BASE)*TILE_W;\n"
 "}\n"
 "static unsigned tile_y(unsigned k){\n"
 "    if(custom_tile(k))return CUSTOM_TILE_Y+(k-tag_count)/TAG_BASE_COLS*TILE_H;\n"
 "    return k<TAG_BASE?TILE_Y+(k/TAG_BASE_COLS)*TILE_H:EXTRA_Y;\n"
 "}\n"
 "static unsigned tile_palette_y(unsigned k){\n"
 "    if(custom_tile(k))return CUSTOM_PALETTE_Y+(k-tag_count)/2;\n"
 "    return k<TAG_BASE?TILE_PALETTE_Y+k:EXTRA_PALETTE_Y+k-TAG_BASE;\n"
 "}\n"
 "static unsigned tile_palette_x(unsigned k){return custom_tile(k)?(k-tag_count)%2*128:0;}\n"
 "static unsigned tile_page(unsigned k){return custom_tile(k)?CUSTOM_PAGE:TILE_PAGE;}", 1),
("    return ((uint32_t)(tile_palette_y(k)<<6)<<16)|(tile_y(k)<<8)|((tile_x(k)-TILE_X)*2);",
 "    return ((uint32_t)(tile_palette_y(k)<<6|tile_palette_x(k)>>4)<<16)|((tile_y(k)&255)<<8)|((tile_x(k)-TILE_X)*2);", 1),
("EXTRA_Y=144, EXTRA_PALETTE_Y=498, EXTRA_MAX=GUEST_MAX-TAG_BASE };",
 "EXTRA_Y=144, EXTRA_PALETTE_Y=498, EXTRA_MAX=TAG_MAX-TAG_BASE };", 1),
("static uint16_t tile_pixels[2][AREA_H*AREA_W],tile_backup[2][AREA_H*AREA_W];",
 "static uint16_t tile_pixels[3][AREA_H*AREA_W],tile_backup[3][AREA_H*AREA_W];\n"
 "static uint16_t custom_palette[CUSTOM_MAX][128];   /* T3CB-PATCH-18: a custom tile's 128 colours */\n"
 "/* T3CB-PATCH-18: the areas in use: Tag tiles, Tag tiles past sixteen, custom tiles. */\n"
 "static int area_used(unsigned a){return a==0?tag_count>0:a==1?tag_count>TAG_BASE:roster_count>tag_count;}", 1),
("static uint16_t palette_pixels[2][AREA_H*AREA_W],palette_backup[2][AREA_H*AREA_W];",
 "static uint16_t palette_pixels[3][AREA_H*AREA_W],palette_backup[3][AREA_H*AREA_W];", 1),
("    for(unsigned i=0;i<n;i++)gr_vram_transfer_in(a[i].x,a[i].y,a[i].w,a[i].h,pixels[i]);",
 "    for(unsigned i=0;i<n;i++)if(area_used(i))gr_vram_transfer_in(a[i].x,a[i].y,a[i].w,a[i].h,pixels[i]);", 1),
("    for(unsigned i=0;i<n;i++)gr_vram_transfer_out(a[i].x,a[i].y,a[i].w,a[i].h,pixels[i]);",
 "    for(unsigned i=0;i<n;i++)if(area_used(i))gr_vram_transfer_out(a[i].x,a[i].y,a[i].w,a[i].h,pixels[i]);", 1),
("static unsigned tile_area_count(void){return roster_count>TAG_BASE?2:1;}",
 "static unsigned tile_area_count(void){return 3;}   /* T3CB-PATCH-18: area_used skips the empty ones */", 1),
("    for(unsigned a=0;a<n;a++) {\n        gr_vram_transfer_out(tile_areas[a].x,",
 "    for(unsigned a=0;a<n;a++) {\n        if(!area_used(a))continue;\n        gr_vram_transfer_out(tile_areas[a].x,", 1),
("static void tiles_upload(void) {\n",
 "/* T3CB-PATCH-18: a custom fighter's tile in at most 128 colours (index 0, transparent, kept),\n"
 " * so two share a palette row: the pair of colours that costs least to merge (by how many\n"
 " * texels use them) merges until 127 are left. */\n"
 "static void custom_tile_pixels(unsigned k,const unsigned char *p,unsigned a,unsigned x,unsigned y0) {\n"
 "    const unsigned char *texels=p+544;\n"
 "    unsigned count[256]={0},owner[256],used=0,s=k-tag_count;\n"
 "    double r[256],g[256],b[256];\n"
 "    for(unsigned i=0;i<TILE_W*2*TILE_H;i++)count[texels[i]]++;\n"
 "    for(unsigned i=0;i<256;i++) {\n"
 "        unsigned c=p[20+i*2]|(unsigned)p[21+i*2]<<8;\n"
 "        owner[i]=i;r[i]=(double)(c&31)*count[i];g[i]=(double)(c>>5&31)*count[i];b[i]=(double)(c>>10&31)*count[i];\n"
 "        if(i && count[i])used++;\n"
 "    }\n"
 "    while(used>127) {\n"
 "        double best=-1;unsigned bi=0,bj=0;\n"
 "        for(unsigned i=1;i<256;i++)if(count[i])for(unsigned j=i+1;j<256;j++)if(count[j]) {\n"
 "            double dr=r[i]/count[i]-r[j]/count[j],dg=g[i]/count[i]-g[j]/count[j],db=b[i]/count[i]-b[j]/count[j];\n"
 "            double cost=(dr*dr+dg*dg+db*db)*count[i]*count[j]/(count[i]+count[j]);\n"
 "            if(best<0 || cost<best){best=cost;bi=i;bj=j;}\n"
 "        }\n"
 "        r[bi]+=r[bj];g[bi]+=g[bj];b[bi]+=b[bj];count[bi]+=count[bj];count[bj]=0;owner[bj]=bi;used--;\n"
 "    }\n"
 "    unsigned char map[256]={0};unsigned next=1;\n"
 "    memset(custom_palette[s],0,sizeof custom_palette[s]);\n"
 "    for(unsigned i=1;i<256;i++)if(count[i]) {\n"
 "        unsigned c=p[20+i*2]|(unsigned)p[21+i*2]<<8;\n"
 "        unsigned rr=(unsigned)(r[i]/count[i]+.5),gg=(unsigned)(g[i]/count[i]+.5),bb=(unsigned)(b[i]/count[i]+.5);\n"
 "        uint16_t colour=(uint16_t)((c&0x8000)|rr|gg<<5|bb<<10);\n"
 "        custom_palette[s][next]=colour?colour:0x8000;   /* black, not transparent */\n"
 "        map[i]=(unsigned char)next++;\n"
 "    }\n"
 "    for(unsigned i=1;i<256;i++){unsigned o=i;while(owner[o]!=o)o=owner[o];map[i]=map[o];}\n"
 "    for(unsigned y=0;y<TILE_H;y++)for(unsigned i=0;i<TILE_W;i++)\n"
 "        tile_pixels[a][(y0+y)*tile_areas[a].w+x+i]=(uint16_t)(map[texels[y*TILE_W*2+i*2]]|map[texels[y*TILE_W*2+i*2+1]]<<8);\n"
 "    memcpy(&palette_pixels[a][(tile_palette_y(k)-palette_areas[a].y)*256+tile_palette_x(k)],custom_palette[s],256);\n"
 "}\n"
 "static void tiles_upload(void) {\n", 1),
("            unsigned a=k>=TAG_BASE,x=tile_x(k)-tile_areas[a].x,y0=tile_y(k)-tile_areas[a].y;\n",
 "            unsigned a=custom_tile(k)?2:k>=TAG_BASE,x=tile_x(k)-tile_areas[a].x,y0=tile_y(k)-tile_areas[a].y;\n"
 "            if(custom_tile(k)){custom_tile_pixels(k,p,a,x,y0);continue;}   /* T3CB-PATCH-18 */\n", 1),
# grey icons borrow full palette rows: the Tag guests'
("    for(unsigned f=0;f<roster_count;f++) {\n        unsigned y=tile_palette_y(f);",
 "    for(unsigned f=0;f<tag_count;f++) {             /* T3CB-PATCH-18: full rows only, the Tag guests' */\n"
 "        unsigned y=tile_palette_y(f);", 1),
("        const unsigned char *p=roster[k].ui+roster[k].ui_offsets[2]+20;\n        uint16_t grey[256];",
 "        const unsigned char *p=roster[k].ui+roster[k].ui_offsets[2]+20;\n"
 "        unsigned char own[512]={0};                /* T3CB-PATCH-18: a custom tile's own 128 colours */\n"
 "        if(custom_tile(k)){memcpy(own,custom_palette[k-tag_count],256);p=own;}\n"
 "        uint16_t grey[256];", 1),
("    if(tiles_active)for(unsigned f=0;f<roster_count;f++)",
 "    if(tiles_active)for(unsigned f=0;f<tag_count;f++)   /* T3CB-PATCH-18: only Tag rows are lent */", 1),
("        psx_mod_write_word(e+4,TILE_PAGE);",
 "        psx_mod_write_word(e+4,tile_page(k));       /* T3CB-PATCH-18 */", 1),
("                tpage=TILE_PAGE;\n",
 "                tpage=tile_page((unsigned)k);         /* T3CB-PATCH-18 */\n", 1),
# --- the cabinet selector's pages ---
("static int page,stock_saved;", "static int stock_saved;", 1),
("static void write_tag_page(void) {\n    for(unsigned k=0;k<roster_count;k++) {",
 "static void write_tag_page(void) {\n    unsigned first=page_first(page),count=page_len(page);\n    for(unsigned k=0;k<count;k++) {", 1),
("        psx_mod_write_half(n+6,GUEST_ID+k);", "        psx_mod_write_half(n+6,GUEST_ID+first+k);", 1),
("        psx_mod_write_byte(CELL_IDS+k,(unsigned char)(GUEST_ID+k));", "        psx_mod_write_byte(CELL_IDS+k,(unsigned char)(GUEST_ID+first+k));", 1),
("    for(unsigned k=roster_count;k<22;k++) {\n        uint32_t n=GRID+k*12;",
 "    for(unsigned k=count;k<22;k++) {\n        uint32_t n=GRID+k*12;", 1),
("    psx_mod_write_word(GRID_COUNT,roster_count);", "    psx_mod_write_word(GRID_COUNT,count);", 1),
("static void switch_page(void) {\n    page=!page;\n    if(page)write_tag_page();else write_stock_page();",
 "static void switch_page(int step) {\n"
 "    int previous=page;\n"
 "    page=(page+step+page_total())%page_total();\n"
 "    if(page)write_tag_page();else write_stock_page();", 1),
("        if(confirmed_page[p]<0){confirmed_page[p]=!page;", "        if(confirmed_page[p]<0){confirmed_page[p]=previous;", 1),
("    fprintf(stderr,\"TTT1 characters: %s page\\n\",page?\"Tag\":\"Tekken 3\");",
 "    fprintf(stderr,\"TTT1 characters: %s page\\n\",page_name(page));", 1),
("        if(edges&(PAD_R2|PAD_L2)) {\n            grid_switch();\n            fprintf(stderr,\"TTT1 characters: %s grid page\\n\",grid_page?\"Tag\":\"Tekken 3\");",
 "        if(edges&(PAD_R2|PAD_L2)) {\n            grid_switch((edges&PAD_R2)?1:-1);\n            fprintf(stderr,\"TTT1 characters: %s grid page\\n\",page_name(grid_page));", 1),
("    if((edges&(PAD_R2|PAD_L2)) && stock_saved)switch_page();",
 "    if((edges&PAD_R2) && stock_saved)switch_page(1);\n    else if((edges&PAD_L2) && stock_saved)switch_page(-1);", 1),
("            if(closed_on_tag && !page)switch_page();", "            if(closed_on_tag && !page)switch_page(closed_on_tag);", 1),
# --- CPU opponents: custom fighters are drawn as the TTT1 guests are (Arcade, Time Attack,
# Survival, Team Battle, Tekken Ball: Expanded's loops over roster_count stay as they are) ---
("    if(nb && boss_one_in && !draw(boss_one_in)) {",
 "    /* T3CB-PATCH-15: custom fighters are among the guests the CPU draws. Test hook:\n"
 "     * TEKKEN3_CPU_STAGE1=<key> makes that fighter the stage 1 opponent */\n"
 "    {\n"
 "        const char *one=getenv(\"TEKKEN3_CPU_STAGE1\");\n"
 "        for(unsigned k=0;one && k<roster_count;k++)if(!strcmp(roster[k].key,one) && GUEST_ID+k!=player) {\n"
 "            list[0]=(unsigned char)(GUEST_ID+k);                   /* stage 1 is loading: the CPU's choice too */\n"
 "            psx_mod_write_half(0x800add5c+(human^1)*2,(uint16_t)(GUEST_ID+k));\n"
 "            if(roster[k].custom){                                      /* and its stage and music (T3CB-PATCH-17) */\n"
 "                arena_pending=1;\n"
 "                arena_value=psx_mod_read_byte(psx_mod_read_word(0x80097d40+roster[k].arena_owner*16)+10);\n"
 "                music_value=psx_mod_read_byte(psx_mod_read_word(0x80097d40+roster[k].music_owner*16)+11);\n"
 "            }\n"
 "            fprintf(stderr,\"TTT1 characters: %s is the CPU's stage 1 opponent (test)\\n\",roster[k].name);\n"
 "        }\n"
 "    }\n"
 "    if(nb && boss_one_in && !draw(boss_one_in)) {", 1),
("static void opponents_tick(unsigned state) {\n",
 "/* T3CB-PATCH-22: a custom fighter's rival. <prefix>-rival.txt, written by the builder: the ID\n"
 " * (0-21) of the stock fighter who meets the custom fighter at stage 9 in Arcade and Time\n"
 " * Attack, where Tekken 3 puts Heihachi (0x800AFB18, 4 bytes per stage). */\n"
 "static int custom_rival_id[CUSTOM_MAX],custom_rival_tried[CUSTOM_MAX];\n"
 "static int custom_rival(unsigned id) {\n"
 "    int k=tekken3_guest_character(id);\n"
 "    if(k<0 || (unsigned)k<tag_count || (unsigned)k-tag_count>=CUSTOM_MAX || !roster[k].custom)return -1;\n"
 "    unsigned c=(unsigned)k-tag_count;\n"
 "    if(!custom_rival_tried[c]) {\n"
 "        custom_rival_tried[c]=1;custom_rival_id[c]=-1;\n"
 "        const char *root=tekken3_ttt1_asset_root();char path[4096];int v;\n"
 "        FILE *f=root && snprintf(path,sizeof path,\"%s/%s-rival.txt\",root,roster[k].prefix)<(int)sizeof path?fopen(path,\"r\"):NULL;\n"
 "        if(f){if(fscanf(f,\"%d\",&v)==1 && v>=0 && v<=21)custom_rival_id[c]=v;fclose(f);}\n"
 "        if(custom_rival_id[c]>=0)fprintf(stderr,\"Custom fighters: %s has rival %d\\n\",roster[k].name,custom_rival_id[c]);\n"
 "    }\n"
 "    return custom_rival_id[c];\n"
 "}\n"
 "static void opponents_tick(unsigned state) {\n", 1),
("    for(unsigned i=0;i<sizeof list;i++)psx_mod_write_byte(OPPONENTS+i,list[i]);\n",
 "    int rival=custom_rival(player);                                   /* T3CB-PATCH-22 */\n"
 "    if(rival>=0){list[8*4]=(unsigned char)rival;list[8*4+1]=0;\n"
 "        for(unsigned i=0;i<8;i++)if(list[i*4]==rival)list[i*4]=13;   /* met first at stage 9: Heihachi takes its place */\n"
 "        fprintf(stderr,\"Custom fighters: rival %d at stage 9\\n\",rival);}\n"
 "    for(unsigned i=0;i<sizeof list;i++)psx_mod_write_byte(OPPONENTS+i,list[i]);\n", 1),
]

MOD = [
("void tekken3_ttt1_before_init(uint32_t model) {\n    initializing++;\n",
 "extern void tekken3_custom_model_install(uint32_t model);\n"
 "void tekken3_ttt1_before_init(uint32_t model) {\n"
 "    tekken3_custom_model_install(model);   /* T3CB-PATCH-10: a custom fighter's own model */\n"
 "    initializing++;\n", 1),
("extern int tekken3_guest_character(unsigned id);\nextern unsigned tekken3_native_moves_id(unsigned player);",
 "extern int tekken3_guest_character(unsigned id);\nextern int tekken3_guest_native(unsigned id);\nextern unsigned tekken3_native_moves_id(unsigned player);", 1),
("    return tekken3_ttt1_roster_enabled()?tekken3_guest_character(psx_mod_read_half(0x800a9240+player*0x188c))>=0:",
 "    /* Custom fighters are guests on the selector but fight as natives. */\n"
 "    return tekken3_ttt1_roster_enabled()?(tekken3_guest_character(psx_mod_read_half(0x800a9240+player*0x188c))>=0 &&\n"
 "        tekken3_guest_native(psx_mod_read_half(0x800a9240+player*0x188c))<0):", 1),
]

COMBAT = [
("void __wrap_func_8002A914(CPUState *cpu) {\n",
 "extern void tekken3_custom_copycat_draw(void);\n"
 "void __wrap_func_8002A914(CPUState *cpu) {\n", 1),
("        for(unsigned p=0;p<2;p++)if(tekken3_guest_draw_moveset(p))ready(p);\n",
 "        for(unsigned p=0;p<2;p++)if(tekken3_guest_draw_moveset(p))ready(p);\n"
 "    /* T3CB-PATCH-5: a custom fighter based on Mokujin draws its moveset each round. */\n"
 "    if((cpu->pc==0 || cpu->pc==0x8002a914) && tekken3_ttt1_roster_enabled())tekken3_custom_copycat_draw();\n", 1),
("enum { CPU_TABLE=0x80098260,",
 "extern int tekken3_guest_native(unsigned id);\n"
 "static unsigned native_row(unsigned id,unsigned fallback){int d=tekken3_guest_native(id);return d<0?fallback:(unsigned)d;}\n"
 "enum { CPU_TABLE=0x80098260,", 1),
("        uint32_t from=CPU_TABLE+(id<CPU_NATIVE_ROWS?id:CPU_DEFAULT_ROW)*CPU_ROW;",
 "        uint32_t from=CPU_TABLE+(id<CPU_NATIVE_ROWS?id:native_row(id,CPU_DEFAULT_ROW))*CPU_ROW;", 1),
("psx_mod_read_word(FORCE_TABLE+(i<FORCE_NATIVE?i:FORCE_DEFAULT*4+i%4)*4)",
 "psx_mod_read_word(FORCE_TABLE+(i<FORCE_NATIVE?i:native_row(i/4,FORCE_DEFAULT)*4+i%4)*4)", 1),
]

NATIVE = [
("    text(k,page?\"TEKKEN TAG TOURNAMENT\":\"TEKKEN 3\",CENTRE_X,top+19,3,5,0x808080);",
 "    text(k,page==2?\"CUSTOM\":page?\"TEKKEN TAG TOURNAMENT\":\"TEKKEN 3\",CENTRE_X,top+19,3,5,0x808080); /* tekken3_guest_native: Character Builder */", 1),
]

EXPANDED_EDITS = {R: ROSTER, M: MOD, C: COMBAT, N: NATIVE}

# --- T3CB-PATCH-13: the renderer probe samples the whole fight (builder's live checks) ---
# TEKKEN3_NATIVE_PROBE_START (calls before recording, default 600), _CALLS (calls recorded,
# default 400) and _EVERY (record 64 calls out of every N, default 0 = all). Defaults keep
# Expanded's behaviour. (marker for the patch status: tekken3_guest_native)
REND = "src/tekken3_ttt1_renderer.c"
RENDER = [
("static void native_probe_record(CPUState *cpu, const uint32_t in[4],",
 "/* T3CB-PATCH-13 (tekken3_guest_native builder): probe window from the environment. */\n"
 "static unsigned probe_env(const char *name, unsigned dflt) {\n"
 "    const char *v=getenv(name); return v && *v ? (unsigned)strtoul(v,NULL,10) : dflt;\n"
 "}\n"
 "static void native_probe_record(CPUState *cpu, const uint32_t in[4],", 1),
("    if(++seen<600) return;",
 "    if(++seen<probe_env(\"TEKKEN3_NATIVE_PROBE_START\",600)) return;\n"
 "    { unsigned every=probe_env(\"TEKKEN3_NATIVE_PROBE_EVERY\",0);\n"
 "      if(every && (seen-probe_env(\"TEKKEN3_NATIVE_PROBE_START\",600))%every>=64) return; }", 1),
("    if(seen>=600+NATIVE_PROBE_CALLS) {",
 "    if(seen>=probe_env(\"TEKKEN3_NATIVE_PROBE_START\",600)+probe_env(\"TEKKEN3_NATIVE_PROBE_CALLS\",NATIVE_PROBE_CALLS)) {", 1),
]
EXPANDED_EDITS[REND] = RENDER
