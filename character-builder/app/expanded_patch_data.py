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
 "static unsigned guest_donor(unsigned id){int d=tekken3_guest_native(id);return d<0?9u:(unsigned)d;}\n", 1),
("static uint32_t guest_desc(unsigned k){return desc+k*DESC_STRIDE;}",
 "/* 22 records fit before name_table; the rest follow its 64 entries. */\n"
 "static uint32_t guest_desc(unsigned k){return k<22?desc+k*DESC_STRIDE:name_table+NAME_TABLE_IDS*4+(k-22)*DESC_STRIDE;}", 1),
("        psx_mod_write_word(body_profiles+(GUEST_ID+k)*4,psx_mod_read_word(0x80096f60+9*4));",
 "        psx_mod_write_word(body_profiles+(GUEST_ID+k)*4,psx_mod_read_word(0x80096f60+(roster[k].custom?roster[k].donor_id:9)*4));", 1),
("            psx_mod_write_byte(model_map+(GUEST_ID+k)*4+c,GUEST_MODEL);",
 "            psx_mod_write_byte(model_map+(GUEST_ID+k)*4+c,roster[k].custom?\n"
 "                psx_mod_read_byte(0x800958c4+roster[k].donor_id*4+c):GUEST_MODEL);", 1),
("tekken3_guest_character(cpu->gpr[5])>=0)cpu->gpr[5]=9;",
 "tekken3_guest_character(cpu->gpr[5])>=0)cpu->gpr[5]=guest_donor(cpu->gpr[5]);", 2),
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
