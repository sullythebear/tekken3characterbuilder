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
 "    unsigned donor_id;            /* its Tekken 3 donor (0..20) */\n", 1),
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
 "/* The guests whose tiles are in VRAM: the last guest page shown. */\n"
 "static int tile_set=1;\n", 1),
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
 " * with <Key>-T3-ui.jui, <Key>-T3-name.4bpp and <Key>-T3-label.txt beside it. */\n"
 "static unsigned custom_slot_model(unsigned k,unsigned c);   /* T3CB-PATCH-9 */\n"
 "static void add_customs(void) {\n"
 "    const char *root=tekken3_ttt1_asset_root();char path[4096];\n"
 "    if(!root || snprintf(path,sizeof path,\"%s/customs.txt\",root)>=(int)sizeof path)return;\n"
 "    FILE *f=fopen(path,\"rb\");if(!f)return;\n"
 "    char line[96];\n"
 "    while(fgets(line,sizeof line,f)) {\n"
 "        char key[32];unsigned donor;\n"
 "        if(sscanf(line,\"%31s %u\",key,&donor)!=2 || donor>20 || roster_index(key)>=0)continue;\n"
 "        if(roster_count-tag_count>=CUSTOM_MAX){fprintf(stderr,\"Custom fighters: %s left out, the Custom page holds %u\\n\",key,(unsigned)CUSTOM_MAX);continue;}\n"
 "        Tekken3Guest *g=&roster[roster_count];\n"
 "        memset(g,0,sizeof *g);\n"
 "        if(!describe(g,key) || !load_ui(g)){\n"
 "            fprintf(stderr,\"Custom fighters: %s left out, its interface files failed validation\\n\",key);\n"
 "            free(g->ui);memset(g,0,sizeof *g);continue;\n"
 "        }\n"
 "        g->custom=1;g->donor_id=donor;g->arena_owner=donor;g->moveset=NO_MOVESET;\n"
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
 "        int d=tekken3_guest_native(id);\n"
 "        copy_guest(table+id*6,0x80027950+(d<0?id:(unsigned)d)*6,6);\n"
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
 "void tekken3_ttt1_roster_tick(void) {\n", 1),
("    patch_tables();\n    unsigned state=psx_mod_read_word(0x800ae204);\n",
 "    patch_tables();\n    custom_fight_probe();\n    copycat_sword();\n    custom_strips();\n    custom_palette_tick();\n    unsigned state=psx_mod_read_word(0x800ae204);\n", 1),
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
 "    if(grid_page && grid_page!=tile_set){tiles_release();tile_set=grid_page;}\n"
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
# --- tiles follow the guest page shown ---
("static unsigned tile_x(unsigned k){return TILE_X+(k<TAG_BASE?k%TAG_BASE_COLS:k-TAG_BASE)*TILE_W;}\n"
 "static unsigned tile_y(unsigned k){return k<TAG_BASE?TILE_Y+(k/TAG_BASE_COLS)*TILE_H:EXTRA_Y;}\n"
 "static unsigned tile_palette_y(unsigned k){return k<TAG_BASE?TILE_PALETTE_Y+k:EXTRA_PALETTE_Y+k-TAG_BASE;}",
 "/* Custom fighters reuse the Tag tiles' slots: only one guest page is up. */\n"
 "static unsigned tile_slot(unsigned k){return k>=tag_count?k-tag_count:k;}\n"
 "static unsigned tile_x(unsigned k){k=tile_slot(k);return TILE_X+(k<TAG_BASE?k%TAG_BASE_COLS:k-TAG_BASE)*TILE_W;}\n"
 "static unsigned tile_y(unsigned k){k=tile_slot(k);return k<TAG_BASE?TILE_Y+(k/TAG_BASE_COLS)*TILE_H:EXTRA_Y;}\n"
 "static unsigned tile_palette_y(unsigned k){k=tile_slot(k);return k<TAG_BASE?TILE_PALETTE_Y+k:EXTRA_PALETTE_Y+k-TAG_BASE;}", 1),
("EXTRA_Y=144, EXTRA_PALETTE_Y=498, EXTRA_MAX=GUEST_MAX-TAG_BASE };",
 "EXTRA_Y=144, EXTRA_PALETTE_Y=498, EXTRA_MAX=TAG_MAX-TAG_BASE };", 1),
("static unsigned tile_area_count(void){return roster_count>TAG_BASE?2:1;}",
 "static unsigned tile_area_count(void){return page_len(tile_set)>TAG_BASE?2:1;}", 1),
("        for(unsigned k=0;k<roster_count;k++) {\n            const unsigned char *p=roster[k].ui+roster[k].ui_offsets[2];\n            unsigned a=k>=TAG_BASE,",
 "        for(unsigned k=page_first(tile_set);k<page_first(tile_set)+page_len(tile_set);k++) {\n"
 "            const unsigned char *p=roster[k].ui+roster[k].ui_offsets[2];\n"
 "            unsigned a=tile_slot(k)>=TAG_BASE,", 1),
("    for(unsigned f=0;f<roster_count;f++) {\n        unsigned y=tile_palette_y(f);",
 "    for(unsigned f=page_first(tile_set);f<page_first(tile_set)+page_len(tile_set);f++) {\n        unsigned y=tile_palette_y(f);", 1),
("    if(tiles_active)for(unsigned f=0;f<roster_count;f++)",
 "    if(tiles_active)for(unsigned f=page_first(tile_set);f<page_first(tile_set)+page_len(tile_set);f++)", 1),
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
 "    if(page && page!=tile_set){tiles_release();tile_set=page;}\n"
 "    if(page)write_tag_page();else write_stock_page();", 1),
("        if(confirmed_page[p]<0){confirmed_page[p]=!page;", "        if(confirmed_page[p]<0){confirmed_page[p]=previous;", 1),
("    fprintf(stderr,\"TTT1 characters: %s page\\n\",page?\"Tag\":\"Tekken 3\");",
 "    fprintf(stderr,\"TTT1 characters: %s page\\n\",page_name(page));", 1),
("        if(edges&(PAD_R2|PAD_L2)) {\n            grid_switch();\n            fprintf(stderr,\"TTT1 characters: %s grid page\\n\",grid_page?\"Tag\":\"Tekken 3\");",
 "        if(edges&(PAD_R2|PAD_L2)) {\n            grid_switch((edges&PAD_R2)?1:-1);\n            fprintf(stderr,\"TTT1 characters: %s grid page\\n\",page_name(grid_page));", 1),
("    if((edges&(PAD_R2|PAD_L2)) && stock_saved)switch_page();",
 "    if((edges&PAD_R2) && stock_saved)switch_page(1);\n    else if((edges&PAD_L2) && stock_saved)switch_page(-1);", 1),
("            if(closed_on_tag && !page)switch_page();", "            if(closed_on_tag && !page)switch_page(closed_on_tag);", 1),
# --- CPU opponents stay TTT1 guests ---
("    for(unsigned k=0;k<roster_count;k++) {\n        if(GUEST_ID+k==player)continue;",
 "    for(unsigned k=0;k<tag_count;k++) {\n        if(GUEST_ID+k==player)continue;", 1),
("for(unsigned k=0;k<roster_count && (boss || guest);k++)", "for(unsigned k=0;k<tag_count && (boss || guest);k++)", 1),
("        for(unsigned k=0;k<roster_count;k++) {\n            int theirs=0;",
 "        for(unsigned k=0;k<tag_count;k++) {\n            int theirs=0;", 1),
("    for(unsigned k=0;k<roster_count;k++)if(GUEST_ID+k!=mine && !hidden_boss(k))pool[n++]=k;",
 "    for(unsigned k=0;k<tag_count;k++)if(GUEST_ID+k!=mine && !hidden_boss(k))pool[n++]=k;", 1),
]

MOD = [
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
