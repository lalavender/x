/* 本文件定义标准 ELF 类型、结构体和宏。
   Copyright (C) 1995-2012 Free Software Foundation, Inc.
   本文件是 GNU C 库的一部分。

   GNU C 库是自由软件；你可以依据自由软件基金会发布的 GNU 宽通用公共许可证
   的条款重新分发和/或修改它，无论是许可证的第 2.1 版，还是（由你选择的）
   任何更新的版本。

   分发 GNU C 库是希望它有用，但不提供任何担保；
   甚至不提供对适销性或特定用途适用性的默示担保。
   详见 GNU 宽通用公共许可证。

   你应当已经随 GNU C 库收到一份 GNU 宽通用公共许可证的副本；
   如果没有，请参见
   <http://www.gnu.org/licenses/>。

  */

#ifndef _ELF_H
#define	_ELF_H 1

#ifndef _WIN32
#include <inttypes.h>
#else
#ifndef __int8_t_defined
#define __int8_t_defined
typedef signed char int8_t;
typedef short int int16_t;
typedef int int32_t;
typedef long long int int64_t;
typedef unsigned char           uint8_t;
typedef unsigned short int      uint16_t;
typedef unsigned int            uint32_t;
typedef unsigned long long int  uint64_t;
#endif
#endif

/* 标准 ELF 类型。  */

/* 16 位量的类型。  */
typedef uint16_t Elf32_Half;
typedef uint16_t Elf64_Half;

/* 有符号和无符号 32 位量的类型。  */
typedef uint32_t Elf32_Word;
typedef	int32_t  Elf32_Sword;
typedef uint32_t Elf64_Word;
typedef	int32_t  Elf64_Sword;

/* 有符号和无符号 64 位量的类型。  */
typedef uint64_t Elf32_Xword;
typedef	int64_t  Elf32_Sxword;
typedef uint64_t Elf64_Xword;
typedef	int64_t  Elf64_Sxword;

/* 地址的类型。  */
typedef uint32_t Elf32_Addr;
typedef uint64_t Elf64_Addr;

/* 文件偏移的类型。  */
typedef uint32_t Elf32_Off;
typedef uint64_t Elf64_Off;

/* 段索引的类型，为 16 位量。  */
typedef uint16_t Elf32_Section;
typedef uint16_t Elf64_Section;

/* 版本符号信息的类型。  */
typedef Elf32_Half Elf32_Versym;
typedef Elf64_Half Elf64_Versym;


/* ELF 文件头。出现在每个 ELF 文件的开头。
 *
 * 64 位 ELF（ELFCLASS64）使用 Elf64_Ehdr，32 位使用 Elf32_Ehdr，两者的区别只在
 * 各字段的宽度与字段顺序（见 elf.h 的 Elf32/Elf64 版本）。TCC 中：
 *   - tcc_object_type() 读取它判断输入文件类型（ET_REL 可重定位 / ET_DYN 共享对象 / ET_EXEC 可执行）；
 *   - tcc_load_object_file()/tcc_load_dll() 依据 e_shoff/e_shnum/e_shentsize 遍历段头表，
 *     依据 e_phoff/e_phnum 遍历程序头表（动态加载时需要）；
 *   - 输出时由 tcc_output_file() 填写（入口地址来自 -e 或运行时入口符号）。
 * e_ident 的前 4 字节是魔数 \x7fELF，第 5 字节指明 32/64 位与字节序。  */

#define EI_NIDENT (16)

typedef struct
{
  unsigned char	e_ident[EI_NIDENT];	/* 魔数和其他信息 */
  Elf32_Half	e_type;			/* 目标文件类型 */
  Elf32_Half	e_machine;		/* 体系结构 */
  Elf32_Word	e_version;		/* 目标文件版本 */
  Elf32_Addr	e_entry;		/* 入口点虚拟地址 */
  Elf32_Off	e_phoff;		/* 程序头表文件偏移 */
  Elf32_Off	e_shoff;		/* 段头表文件偏移 */
  Elf32_Word	e_flags;		/* 处理器特定的标志 */
  Elf32_Half	e_ehsize;		/* ELF 头大小的字节数 */
  Elf32_Half	e_phentsize;		/* 程序头表条目大小 */
  Elf32_Half	e_phnum;		/* 程序头表条目计数 */
  Elf32_Half	e_shentsize;		/* 段头表条目大小 */
  Elf32_Half	e_shnum;		/* 段头表条目计数 */
  Elf32_Half	e_shstrndx;		/* 段头字符串表索引 */
} Elf32_Ehdr;

typedef struct
{
  unsigned char	e_ident[EI_NIDENT];	/* 魔数和其他信息 */
  Elf64_Half	e_type;			/* 目标文件类型 */
  Elf64_Half	e_machine;		/* 体系结构 */
  Elf64_Word	e_version;		/* 目标文件版本 */
  Elf64_Addr	e_entry;		/* 入口点虚拟地址 */
  Elf64_Off	e_phoff;		/* 程序头表文件偏移 */
  Elf64_Off	e_shoff;		/* 段头表文件偏移 */
  Elf64_Word	e_flags;		/* 处理器特定的标志 */
  Elf64_Half	e_ehsize;		/* ELF 头大小的字节数 */
  Elf64_Half	e_phentsize;		/* 程序头表条目大小 */
  Elf64_Half	e_phnum;		/* 程序头表条目计数 */
  Elf64_Half	e_shentsize;		/* 段头表条目大小 */
  Elf64_Half	e_shnum;		/* 段头表条目计数 */
  Elf64_Half	e_shstrndx;		/* 段头字符串表索引 */
} Elf64_Ehdr;

/* e_ident 数组中的字段。EI_* 宏是进入该数组的 索引。每个 EI_* 宏下的宏是该字节可能
   具有的值。
  */

#define EI_MAG0		0		/* 文件标识字节 0 索引 */
#define ELFMAG0		0x7f		/* 魔数字节 0 */

#define EI_MAG1		1		/* 文件标识字节 1 索引 */
#define ELFMAG1		'E'		/* 魔数字节 1 */

#define EI_MAG2		2		/* 文件标识字节 2 索引 */
#define ELFMAG2		'L'		/* 魔数字节 2 */

#define EI_MAG3		3		/* 文件标识字节 3 索引 */
#define ELFMAG3		'F'		/* 魔数字节 3 */

/* 各标识字节的组合，便于作为一个字来测试。  */
#define	ELFMAG		"\177ELF"
#define	SELFMAG		4

#define EI_CLASS	4		/* 文件类别字节索引 */
#define ELFCLASSNONE	0		/* 无效类别 */
#define ELFCLASS32	1		/* 32 位对象 */
#define ELFCLASS64	2		/* 64 位对象 */
#define ELFCLASSNUM	3

#define EI_DATA		5		/* 数据编码字节索引 */
#define ELFDATANONE	0		/* 无效数据编码 */
#define ELFDATA2LSB	1		/* 二进制补码，小端 */
#define ELFDATA2MSB	2		/* 二进制补码，大端 */
#define ELFDATANUM	3

#define EI_VERSION	6		/* 文件版本字节索引 */
					/* 值必须为 EV_CURRENT */

#define EI_OSABI	7		/* OS ABI 标识 */
#define ELFOSABI_NONE		0	/* UNIX System V ABI */
#define ELFOSABI_SYSV		0	/* 别名。  */
#define ELFOSABI_HPUX		1	/* HP-UX */
#define ELFOSABI_NETBSD		2	/* NetBSD.  */
#define ELFOSABI_GNU		3	/* 目标文件使用 GNU ELF 扩展。  */
#define ELFOSABI_LINUX		ELFOSABI_GNU /* 兼容性别名。  */
#define ELFOSABI_SOLARIS	6	/* Sun Solaris.  */
#define ELFOSABI_AIX		7	/* IBM AIX.  */
#define ELFOSABI_IRIX		8	/* SGI Irix.  */
#define ELFOSABI_FREEBSD	9	/* FreeBSD.  */
#define ELFOSABI_TRU64		10	/* Compaq TRU64 UNIX.  */
#define ELFOSABI_MODESTO	11	/* Novell Modesto.  */
#define ELFOSABI_OPENBSD	12	/* OpenBSD.  */
#define ELFOSABI_ARM_AEABI	64	/* ARM EABI */
#define ELFOSABI_ARM		97	/* ARM */
#define ELFOSABI_STANDALONE	255	/* 独立（嵌入式）应用程序 */

#define EI_ABIVERSION	8		/* ABI 版本 */

#define EI_PAD		9		/* 填充字节的字节索引 */

/* e_type（目标文件类型）的合法值。  */

#define ET_NONE		0		/* 无文件类型 */
#define ET_REL		1		/* 可重定位文件 */
#define ET_EXEC		2		/* 可执行文件 */
#define ET_DYN		3		/* 共享目标文件 */
#define ET_CORE		4		/* 核心文件 */
#define	ET_NUM		5		/* 已定义类型的数量 */
#define ET_LOOS		0xfe00		/* OS 特定范围起始 */
#define ET_HIOS		0xfeff		/* OS 特定范围结束 */
#define ET_LOPROC	0xff00		/* 处理器特定范围起始 */
#define ET_HIPROC	0xffff		/* 处理器特定范围结束 */

/* e_machine（体系结构）的合法值。  */

#define EM_NONE		 0		/* 无机器 */
#define EM_M32		 1		/* AT&T WE 32100 */
#define EM_SPARC	 2		/* SUN SPARC */
#define EM_386		 3		/* Intel 80386 */
#define EM_68K		 4		/* Motorola m68k 系列 */
#define EM_88K		 5		/* Motorola m88k 系列 */
#define EM_860		 7		/* Intel 80860 */
#define EM_MIPS		 8		/* MIPS R3000 大端 */
#define EM_S370		 9		/* IBM System/370 */
#define EM_MIPS_RS3_LE	10		/* MIPS R3000 小端 */

#define EM_PARISC	15		/* HPPA */
#define EM_VPP500	17		/* Fujitsu VPP500 */
#define EM_SPARC32PLUS	18		/* Sun 的 "v8plus" */
#define EM_960		19		/* Intel 80960 */
#define EM_PPC		20		/* PowerPC */
#define EM_PPC64	21		/* PowerPC 64 位 */
#define EM_S390		22		/* IBM S390 */

#define EM_V800		36		/* NEC V800 系列 */
#define EM_FR20		37		/* Fujitsu FR20 */
#define EM_RH32		38		/* TRW RH-32 */
#define EM_RCE		39		/* Motorola RCE */
#define EM_ARM		40		/* ARM */
#define EM_FAKE_ALPHA	41		/* Digital Alpha */
#define EM_SH		42		/* Hitachi SH */
#define EM_SPARCV9	43		/* SPARC v9 64 位 */
#define EM_TRICORE	44		/* Siemens Tricore */
#define EM_ARC		45		/* Argonaut RISC Core */
#define EM_H8_300	46		/* Hitachi H8/300 */
#define EM_H8_300H	47		/* Hitachi H8/300H */
#define EM_H8S		48		/* Hitachi H8S */
#define EM_H8_500	49		/* Hitachi H8/500 */
#define EM_IA_64	50		/* Intel Merced */
#define EM_MIPS_X	51		/* Stanford MIPS-X */
#define EM_COLDFIRE	52		/* Motorola Coldfire */
#define EM_68HC12	53		/* Motorola M68HC12 */
#define EM_MMA		54		/* Fujitsu MMA 多媒体加速器*/
#define EM_PCP		55		/* Siemens PCP */
#define EM_NCPU		56		/* Sony nCPU 嵌入式 RISC */
#define EM_NDR1		57		/* Denso NDR1 微处理器 */
#define EM_STARCORE	58		/* Motorola Start*Core 处理器 */
#define EM_ME16		59		/* Toyota ME16 处理器 */
#define EM_ST100	60		/* STMicroelectronic ST100 处理器 */
#define EM_TINYJ	61		/* Advanced Logic Corp. Tinyj 嵌入式系列*/
#define EM_X86_64	62		/* AMD x86-64 体系结构 */
#define EM_PDSP		63		/* Sony DSP 处理器 */

#define EM_FX66		66		/* Siemens FX66 微控制器 */
#define EM_ST9PLUS	67		/* STMicroelectronics ST9+ 8/16 微控制器 */
#define EM_ST7		68		/* STMicroelectronics ST7 8 位微控制器 */
#define EM_68HC16	69		/* Motorola MC68HC16 微控制器 */
#define EM_68HC11	70		/* Motorola MC68HC11 微控制器 */
#define EM_68HC08	71		/* Motorola MC68HC08 微控制器 */
#define EM_68HC05	72		/* Motorola MC68HC05 微控制器 */
#define EM_SVX		73		/* Silicon Graphics SVx */
#define EM_ST19		74		/* STMicroelectronics ST19 8 位微控制器 */
#define EM_VAX		75		/* Digital VAX */
#define EM_CRIS		76		/* Axis Communications 32 位嵌入式处理器 */
#define EM_JAVELIN	77		/* Infineon Technologies 32 位嵌入式处理器 */
#define EM_FIREPATH	78		/* Element 14 64 位 DSP 处理器 */
#define EM_ZSP		79		/* LSI Logic 16 位 DSP 处理器 */
#define EM_MMIX		80		/* Donald Knuth 的教学用 64 位处理器 */
#define EM_HUANY	81		/* Harvard University 机器无关目标文件 */
#define EM_PRISM	82		/* SiTera Prism */
#define EM_AVR		83		/* Atmel AVR 8 位微控制器 */
#define EM_FR30		84		/* Fujitsu FR30 */
#define EM_D10V		85		/* Mitsubishi D10V */
#define EM_D30V		86		/* Mitsubishi D30V */
#define EM_V850		87		/* NEC v850 */
#define EM_M32R		88		/* Mitsubishi M32R */
#define EM_MN10300	89		/* Matsushita MN10300 */
#define EM_MN10200	90		/* Matsushita MN10200 */
#define EM_PJ		91		/* picoJava */
#define EM_OPENRISC	92		/* OpenRISC 32 位嵌入式处理器 */
#define EM_ARC_A5	93		/* ARC Cores Tangent-A5 */
#define EM_XTENSA	94		/* Tensilica Xtensa 体系结构 */
#define EM_AARCH64	183		/* ARM AARCH64 */
#define EM_TILEPRO	188		/* Tilera TILEPro */
#define EM_TILEGX	191		/* Tilera TILE-Gx */
#define EM_NUM		192

/* 如果有必要分配新的非官方 EM_* 值，请 挑选较大的随机数（0x8523、0xa7f2
   等）以尽可能减小 与官方或非 GNU 非官方值冲突的可能。
  */

#define EM_ALPHA	0x9026
#define EM_C60		0x9c60

/* e_version（版本）的合法值。  */

#define EV_NONE		0		/* 无效 ELF 版本 */
#define EV_CURRENT	1		/* 当前版本 */
#define EV_NUM		2

/* 段头（section header）。描述一个段的名字、类型、大小、对齐与在文件中的位置。
 *
 * 段头表本身也是文件的一部分：e_shoff 指向它的起点，e_shstrndx 指出哪个段存放段名
 * 字符串（sh_name 是该字符串表中的下标）。
 * TCC 中 Section 结构（见 tcc.h）在内存里累积数据，输出阶段再由 tccelf.c 把它的
 * 字段对号入座写成段头；读入 .o/.so 时则反向填充。
 * sh_link/sh_info 的含义随 sh_type 而定（如重定位段的 sh_link 指向符号表、
 * sh_info 指出作用于哪个段），sh_entsize 在段是表结构时给出单个条目大小。  */

typedef struct
{
  Elf32_Word	sh_name;		/* 段名（字符串表索引） */
  Elf32_Word	sh_type;		/* 段类型 */
  Elf32_Word	sh_flags;		/* 段标志 */
  Elf32_Addr	sh_addr;		/* 段执行时的虚拟地址 */
  Elf32_Off	sh_offset;		/* 段文件偏移 */
  Elf32_Word	sh_size;		/* 段大小（字节） */
  Elf32_Word	sh_link;		/* 链接到另一个段 */
  Elf32_Word	sh_info;		/* 附加段信息 */
  Elf32_Word	sh_addralign;		/* 段对齐 */
  Elf32_Word	sh_entsize;		/* 段持有表时的条目大小 */
} Elf32_Shdr;

typedef struct
{
  Elf64_Word	sh_name;		/* 段名（字符串表索引） */
  Elf64_Word	sh_type;		/* 段类型 */
  Elf64_Xword	sh_flags;		/* 段标志 */
  Elf64_Addr	sh_addr;		/* 段执行时的虚拟地址 */
  Elf64_Off	sh_offset;		/* 段文件偏移 */
  Elf64_Xword	sh_size;		/* 段大小（字节） */
  Elf64_Word	sh_link;		/* 链接到另一个段 */
  Elf64_Word	sh_info;		/* 附加段信息 */
  Elf64_Xword	sh_addralign;		/* 段对齐 */
  Elf64_Xword	sh_entsize;		/* 段持有表时的条目大小 */
} Elf64_Shdr;

/* 特殊段索引。  */

#define SHN_UNDEF	0		/* 未定义段 */
#define SHN_LORESERVE	0xff00		/* 保留索引的起始 */
#define SHN_LOPROC	0xff00		/* 处理器特定的起始 */
#define SHN_BEFORE	0xff00		/* 将段排在其他所有段之前 （Solaris）。
  */
#define SHN_AFTER	0xff01		/* 将段排在其他所有段之后 （Solaris）。
  */
#define SHN_HIPROC	0xff1f		/* 处理器特定的结束 */
#define SHN_LOOS	0xff20		/* OS 特定的起始 */
#define SHN_HIOS	0xff3f		/* OS 特定的结束 */
#define SHN_ABS		0xfff1		/* 关联的符号是绝对的 */
#define SHN_COMMON	0xfff2		/* 关联的符号是公共的 */
#define SHN_XINDEX	0xffff		/* 索引位于附加表中。  */
#define SHN_HIRESERVE	0xffff		/* 保留索引的结束 */

/* sh_type（段类型）的合法值。  */

#define SHT_NULL	  0		/* 段头表条目未使用 */
#define SHT_PROGBITS	  1		/* 程序数据 */
#define SHT_SYMTAB	  2		/* 符号表 */
#define SHT_STRTAB	  3		/* 字符串表 */
#define SHT_RELA	  4		/* 带加数的重定位条目 */
#define SHT_HASH	  5		/* 符号哈希表 */
#define SHT_DYNAMIC	  6		/* 动态链接信息 */
#define SHT_NOTE	  7		/* 注释 */
#define SHT_NOBITS	  8		/* 无数据的程序空间（bss） */
#define SHT_REL		  9		/* 不带加数的重定位条目 */
#define SHT_SHLIB	  10		/* 保留 */
#define SHT_DYNSYM	  11		/* 动态链接器符号表 */
#define SHT_INIT_ARRAY	  14		/* 构造函数数组 */
#define SHT_FINI_ARRAY	  15		/* 析构函数数组 */
#define SHT_PREINIT_ARRAY 16		/* 预构造函数数组 */
#define SHT_GROUP	  17		/* 段组 */
#define SHT_SYMTAB_SHNDX  18		/* 扩展段索引 */
#define	SHT_NUM		  19		/* 已定义类型的数量。  */
#define SHT_LOOS	  0x60000000	/* OS 特定的起始。  */
#define SHT_GNU_ATTRIBUTES 0x6ffffff5	/* 目标文件属性。  */
#define SHT_GNU_HASH	  0x6ffffff6	/* GNU 风格的哈希表。  */
#define SHT_GNU_LIBLIST	  0x6ffffff7	/* 预链接库列表 */
#define SHT_CHECKSUM	  0x6ffffff8	/* DSO 内容的校验和。  */
#define SHT_LOSUNW	  0x6ffffffa	/* Sun 特定的下界。  */
#define SHT_SUNW_move	  0x6ffffffa
#define SHT_SUNW_COMDAT   0x6ffffffb
#define SHT_SUNW_syminfo  0x6ffffffc
#define SHT_GNU_verdef	  0x6ffffffd	/* 版本定义段。  */
#define SHT_GNU_verneed	  0x6ffffffe	/* 版本需求段。  */
#define SHT_GNU_versym	  0x6fffffff	/* 版本符号表。  */
#define SHT_HISUNW	  0x6fffffff	/* Sun 特定的上界。  */
#define SHT_HIOS	  0x6fffffff	/* OS 特定类型的结束 */
#define SHT_LOPROC	  0x70000000	/* 处理器特定的起始 */
#define SHT_HIPROC	  0x7fffffff	/* 处理器特定的结束 */
#define SHT_LOUSER	  0x80000000	/* 应用程序特定的起始 */
#define SHT_HIUSER	  0x8fffffff	/* 应用程序特定的结束 */

/* sh_flags（段标志）的合法值。  */

#define SHF_WRITE	     (1 << 0)	/* 可写 */
#define SHF_ALLOC	     (1 << 1)	/* 执行期间占用内存 */
#define SHF_EXECINSTR	     (1 << 2)	/* 可执行 */
#define SHF_MERGE	     (1 << 4)	/* 可能被合并 */
#define SHF_STRINGS	     (1 << 5)	/* 包含以 nul 结尾的字符串 */
#define SHF_INFO_LINK	     (1 << 6)	/* `sh_info' 包含 SHT 索引 */
#define SHF_LINK_ORDER	     (1 << 7)	/* 合并后保留顺序 */
#define SHF_OS_NONCONFORMING (1 << 8)	/* 需要非标准 OS 特定 处理
 */
#define SHF_GROUP	     (1 << 9)	/* 段是某个组的成员。  */
#define SHF_TLS		     (1 << 10)	/* 段持有线程局部数据。  */
#define SHF_COMPRESSED	     (1 << 11)	/* 含压缩数据的段。 */
#define SHF_MASKOS	     0x0ff00000	/* OS 特定。  */
#define SHF_MASKPROC	     0xf0000000	/* 处理器特定 */
#define SHF_ORDERED	     (1 << 30)	/* 特殊排序要求 （Solaris）。
  */
#define SHF_EXCLUDE	     (1 << 31)	/* 除非被引用或分配，否则段 被排除（Solaris）。
*/

/* 段组处理。  */
#define GRP_COMDAT	0x1		/* 将组标记为 COMDAT。  */

/* 符号表条目（symbol table entry）。
 *
 * 每个段类型为 SHT_SYMTAB 或 SHT_DYNSYM 的段都是一张本结构的数组，st_name 是符号名
 * 在其关联字符串表（sh_link 所指段）中的下标。
 * 关键约定：st_value 在可重定位文件中是段内偏移，需配合 st_shndx（所在段号）才有意义；
 * SHN_UNDEF 表示该符号在本文件未定义（需要链接器解析），SHN_ABS 表示绝对值。
 * st_info 由 ELF32/64_ST_BIND（绑定：LOCAL/GLOBAL/WEAK）与 ST_TYPE（类型：
 * OBJECT/FUNC/SECTION/FILE...）打包而成，st_other 低 2 位是可见性（STV_*）。
 * TCC 用 put_elf_sym()/set_elf_sym() 写入，用 find_elf_sym() 查找；Sym.c 字段保存
 * 该符号在本表中的下标。  */


typedef struct
{
  Elf32_Word	st_name;		/* 符号名（字符串表索引） */
  Elf32_Addr	st_value;		/* 符号值 */
  Elf32_Word	st_size;		/* 符号大小 */
  unsigned char	st_info;		/* 符号类型和绑定 */
  unsigned char	st_other;		/* 符号可见性 */
  Elf32_Section	st_shndx;		/* 段索引 */
} Elf32_Sym;

typedef struct
{
  Elf64_Word	st_name;		/* 符号名（字符串表索引） */
  unsigned char	st_info;		/* 符号类型和绑定 */
  unsigned char st_other;		/* 符号可见性 */
  Elf64_Section	st_shndx;		/* 段索引 */
  Elf64_Addr	st_value;		/* 符号值 */
  Elf64_Xword	st_size;		/* 符号大小 */
} Elf64_Sym;

/* syminfo 段（如果存在）包含关于每个 动态符号的附加信息。
  */

typedef struct
{
  Elf32_Half si_boundto;		/* 直接绑定，符号绑定到 */
  Elf32_Half si_flags;			/* 每个符号的标志 */
} Elf32_Syminfo;

typedef struct
{
  Elf64_Half si_boundto;		/* 直接绑定，符号绑定到 */
  Elf64_Half si_flags;			/* 每个符号的标志 */
} Elf64_Syminfo;

/* si_boundto 的可能值。  */
#define SYMINFO_BT_SELF		0xffff	/* 符号绑定到自身 */
#define SYMINFO_BT_PARENT	0xfffe	/* 符号绑定到父级 */
#define SYMINFO_BT_LOWRESERVE	0xff00	/* 保留条目的起始 */

/* si_flags 的可能位掩码。  */
#define SYMINFO_FLG_DIRECT	0x0001	/* 直接绑定符号 */
#define SYMINFO_FLG_PASSTHRU	0x0002	/* 转译器的直通符号 */
#define SYMINFO_FLG_COPY	0x0004	/* 符号是副本重定位 */
#define SYMINFO_FLG_LAZYLOAD	0x0008	/* 符号绑定到要延迟 加载的对象
 */
/* Syminfo 版本值。  */
#define SYMINFO_NONE		0
#define SYMINFO_CURRENT		1
#define SYMINFO_NUM		2


/* 如何提取和插入 st_info 字段中持有的信息。  */

#define ELF32_ST_BIND(val)		(((unsigned char) (val)) >> 4)
#define ELF32_ST_TYPE(val)		((val) & 0xf)
#define ELF32_ST_INFO(bind, type)	(((bind) << 4) + ((type) & 0xf))

/* Elf32_Sym 和 Elf64_Sym 都使用同一个单字节 st_info 字段。  */
#define ELF64_ST_BIND(val)		ELF32_ST_BIND (val)
#define ELF64_ST_TYPE(val)		ELF32_ST_TYPE (val)
#define ELF64_ST_INFO(bind, type)	ELF32_ST_INFO ((bind), (type))

/* st_info 的 ST_BIND 子字段（符号绑定）的合法值。  */

#define STB_LOCAL	0		/* 局部符号 */
#define STB_GLOBAL	1		/* 全局符号 */
#define STB_WEAK	2		/* 弱符号 */
#define	STB_NUM		3		/* 已定义类型的数量。  */
#define STB_LOOS	10		/* OS 特定的起始 */
#define STB_GNU_UNIQUE	10		/* 唯一符号。  */
#define STB_HIOS	12		/* OS 特定的结束 */
#define STB_LOPROC	13		/* 处理器特定的起始 */
#define STB_HIPROC	15		/* 处理器特定的结束 */

/* st_info 的 ST_TYPE 子字段（符号类型）的合法值。  */

#define STT_NOTYPE	0		/* 符号类型未指定 */
#define STT_OBJECT	1		/* 符号是数据对象 */
#define STT_FUNC	2		/* 符号是代码对象 */
#define STT_SECTION	3		/* 符号关联到某个段 */
#define STT_FILE	4		/* 符号名是文件名 */
#define STT_COMMON	5		/* 符号是公共数据对象 */
#define STT_TLS		6		/* 符号是线程局部数据对象*/
#define	STT_NUM		7		/* 已定义类型的数量。  */
#define STT_LOOS	10		/* OS 特定的起始 */
#define STT_GNU_IFUNC	10		/* 符号是间接代码对象 */
#define STT_HIOS	12		/* OS 特定的结束 */
#define STT_LOPROC	13		/* 处理器特定的起始 */
#define STT_HIPROC	15		/* 处理器特定的结束 */


/* 符号表索引位于符号哈希表段的哈希桶和链表中。
   这个特殊索引值表示链的末尾，意味着在该桶中找不到 更多符号。
  */

#define STN_UNDEF	0		/* 链的末尾。  */


/* 如何提取和插入 st_other 字段中持有的信息。  */

#define ELF32_ST_VISIBILITY(o)	((o) & 0x03)

/* 对 ELF64 而言定义相同。  */
#define ELF64_ST_VISIBILITY(o)	ELF32_ST_VISIBILITY (o)

/* 编码在 st_other 字段中的符号可见性规范。  */
#define STV_DEFAULT	0		/* 默认符号可见性规则 */
#define STV_INTERNAL	1		/* 处理器特定的隐藏类别 */
#define STV_HIDDEN	2		/* 符号在其他模块中不可用 */
#define STV_PROTECTED	3		/* 不可抢占，不导出 */


/* 重定位表条目：告诉链接器“把某个位置上的值按某规则改写”。
 *
 * 两种形式：SHT_REL 段的条目 r_offset/r_info 不带加数；SHT_RELA 段的条目多一个
 * r_addend，用于 AArch64 这类需要显式加数的架构（TCC 在 64 位目标上统一使用 Rela）。
 * r_offset 是待修改位置（可重定位文件中为段内偏移，可执行/共享对象中为虚拟地址）；
 * r_info 打包了符号下标与重定位类型，用 ELF32/64_R_SYM、ELF32/64_R_TYPE 拆解，
 * 类型取值见本文件后面的 R_AARCH64_* 等定义。
 * TCC 中由 greloc()/greloca() 记录，relocate_section() 在输出或加载时落实。  */

typedef struct
{
  Elf32_Addr	r_offset;		/* 地址 */
  Elf32_Word	r_info;			/* 重定位类型和符号索引 */
} Elf32_Rel;

/* 我见过 Elf64_Rel 和 Elf64_Rela 结构体的两种 不同定义，所以在
   Novell（或无论谁）把问题 理清之前，我们先不写它们。
  */
/* 至少以下内容用在 Sparc v9、MIPS 和 Alpha 上。  */

typedef struct
{
  Elf64_Addr	r_offset;		/* 地址 */
  Elf64_Xword	r_info;			/* 重定位类型和符号索引 */
} Elf64_Rel;

/* 带加数的重定位表条目（位于类型为 SHT_RELA 的段中）。  */

typedef struct
{
  Elf32_Addr	r_offset;		/* 地址 */
  Elf32_Word	r_info;			/* 重定位类型和符号索引 */
  Elf32_Sword	r_addend;		/* 加数 */
} Elf32_Rela;

typedef struct
{
  Elf64_Addr	r_offset;		/* 地址 */
  Elf64_Xword	r_info;			/* 重定位类型和符号索引 */
  Elf64_Sxword	r_addend;		/* 加数 */
} Elf64_Rela;

/* 如何提取和插入 r_info 字段中持有的信息。  */

#define ELF32_R_SYM(val)		((val) >> 8)
#define ELF32_R_TYPE(val)		((val) & 0xff)
#define ELF32_R_INFO(sym, type)		(((sym) << 8) + ((type) & 0xff))

#define ELF64_R_SYM(i)			((i) >> 32)
#define ELF64_R_TYPE(i)			((i) & 0xffffffff)
#define ELF64_R_INFO(sym,type)		((((Elf64_Xword) (sym)) << 32) + (type))

/* 程序段头（program header）。描述“加载器如何把文件映射进内存”的一个内存段。
 *
 * 它只出现在可执行文件与共享对象中（可重定位 .o 没有）。p_offset/p_filesz 描述文件里
 * 的原始数据，p_vaddr/p_memsz 描述运行时的内存映像，二者之差即 .bss 未被初始化的尾部；
 * p_flags 是 PF_R/PF_W/PF_X 权限位；p_align 要求 vaddr 与 offset 同余。
 * TCC 输出时由 set_elf_sections() 按段顺序划分内存段，并填写 PT_LOAD、PT_DYNAMIC、
 * PT_INTERP、PT_GNU_STACK 等条目。  */

typedef struct
{
  Elf32_Word	p_type;			/* 段类型 */
  Elf32_Off	p_offset;		/* 段文件偏移 */
  Elf32_Addr	p_vaddr;		/* 段虚拟地址 */
  Elf32_Addr	p_paddr;		/* 段物理地址 */
  Elf32_Word	p_filesz;		/* 段在文件中的大小 */
  Elf32_Word	p_memsz;		/* 段在内存中的大小 */
  Elf32_Word	p_flags;		/* 段标志 */
  Elf32_Word	p_align;		/* 段对齐 */
} Elf32_Phdr;

typedef struct
{
  Elf64_Word	p_type;			/* 段类型 */
  Elf64_Word	p_flags;		/* 段标志 */
  Elf64_Off	p_offset;		/* 段文件偏移 */
  Elf64_Addr	p_vaddr;		/* 段虚拟地址 */
  Elf64_Addr	p_paddr;		/* 段物理地址 */
  Elf64_Xword	p_filesz;		/* 段在文件中的大小 */
  Elf64_Xword	p_memsz;		/* 段在内存中的大小 */
  Elf64_Xword	p_align;		/* 段对齐 */
} Elf64_Phdr;

/* e_phnum 的特殊值。这表示程序头的实际数量 太大而无法放入 e_phnum。真正的值 位于 0
   号段的 sh_info 字段中。
  */

#define PN_XNUM		0xffff

/* p_type（段类型）的合法值。  */

#define	PT_NULL		0		/* 程序头表条目未使用 */
#define PT_LOAD		1		/* 可加载程序段 */
#define PT_DYNAMIC	2		/* 动态链接信息 */
#define PT_INTERP	3		/* 程序解释器 */
#define PT_NOTE		4		/* 辅助信息 */
#define PT_SHLIB	5		/* 保留 */
#define PT_PHDR		6		/* 头表自身的条目 */
#define PT_TLS		7		/* 线程局部存储段 */
#define	PT_NUM		8		/* 已定义类型的数量 */
#define PT_LOOS		0x60000000	/* OS 特定的起始 */
#define PT_GNU_EH_FRAME	0x6474e550	/* GCC .eh_frame_hdr 段 */
#define PT_GNU_STACK	0x6474e551	/* 表示栈可执行 */
#define PT_GNU_RELRO	0x6474e552	/* 重定位后只读 */
#define PT_LOSUNW	0x6ffffffa
#define PT_SUNWBSS	0x6ffffffa	/* Sun 特定段 */
#define PT_SUNWSTACK	0x6ffffffb	/* 栈段 */
#define PT_HISUNW	0x6fffffff
#define PT_HIOS		0x6fffffff	/* OS 特定的结束 */
#define PT_LOPROC	0x70000000	/* 处理器特定的起始 */
#define PT_HIPROC	0x7fffffff	/* 处理器特定的结束 */

/* p_flags（段标志）的合法值。  */

#define PF_X		(1 << 0)	/* 段可执行 */
#define PF_W		(1 << 1)	/* 段可写 */
#define PF_R		(1 << 2)	/* 段可读 */
#define PF_MASKOS	0x0ff00000	/* OS 特定 */
#define PF_MASKPROC	0xf0000000	/* 处理器特定 */

/* 核心文件的注释段描述符类型的合法值。 */

#define NT_PRSTATUS	1		/* 包含 prstatus 结构体的副本 */
#define NT_FPREGSET	2		/* 包含 fpregset 结构体的副本 */
#define NT_PRPSINFO	3		/* 包含 prpsinfo 结构体的副本 */
#define NT_PRXREG	4		/* 包含 prxregset 结构体的副本 */
#define NT_TASKSTRUCT	4		/* 包含 task 结构体的副本 */
#define NT_PLATFORM	5		/* 来自 sysinfo(SI_PLATFORM) 的字符串 */
#define NT_AUXV		6		/* 包含 auxv 数组的副本 */
#define NT_GWINDOWS	7		/* 包含 gwindows 结构体的副本 */
#define NT_ASRS		8		/* 包含 asrset 结构体的副本 */
#define NT_PSTATUS	10		/* 包含 pstatus 结构体的副本 */
#define NT_PSINFO	13		/* 包含 psinfo 结构体的副本 */
#define NT_PRCRED	14		/* 包含 prcred 结构体的副本 */
#define NT_UTSNAME	15		/* 包含 utsname 结构体的副本 */
#define NT_LWPSTATUS	16		/* 包含 lwpstatus 结构体的副本 */
#define NT_LWPSINFO	17		/* 包含 lwpinfo 结构体的副本 */
#define NT_PRFPXREG	20		/* 包含 fprxregset 结构体的副本 */
#define NT_PRXFPREG	0x46e62b7f	/* 包含 user_fxsr_struct 的副本 */
#define NT_PPC_VMX	0x100		/* PowerPC Altivec/VMX 寄存器 */
#define NT_PPC_SPE	0x101		/* PowerPC SPE/EVR 寄存器 */
#define NT_PPC_VSX	0x102		/* PowerPC VSX 寄存器 */
#define NT_386_TLS	0x200		/* i386 TLS 槽位（struct user_desc） */
#define NT_386_IOPERM	0x201		/* x86 io 权限位图（1=拒绝） */
#define NT_X86_XSTATE	0x202		/* 使用 xsave 的 x86 扩展状态 */
#define NT_S390_HIGH_GPRS	0x300	/* s390 寄存器高半部分 */
#define NT_S390_TIMER	0x301		/* s390 定时器寄存器 */
#define NT_S390_TODCMP	0x302		/* s390 TOD 时钟比较寄存器 */
#define NT_S390_TODPREG	0x303		/* s390 TOD 可编程寄存器 */
#define NT_S390_CTRS	0x304		/* s390 控制寄存器 */
#define NT_S390_PREFIX	0x305		/* s390 前缀寄存器 */
#define NT_S390_LAST_BREAK	0x306	/* s390 中断事件地址 */
#define NT_S390_SYSTEM_CALL	0x307	/* s390 系统调用重启数据 */
#define NT_ARM_VFP	0x400		/* ARM VFP/NEON 寄存器 */
#define NT_ARM_TLS	0x401		/* ARM TLS 寄存器 */
#define NT_ARM_HW_BREAK	0x402		/* ARM 硬件断点寄存器 */
#define NT_ARM_HW_WATCH	0x403		/* ARM 硬件观察点寄存器 */

/* 目标文件的注释段描述符类型的合法值。  */

#define NT_VERSION	1		/* 包含版本字符串。  */


/* 动态段条目（.dynamic 中的一项）：tag + 值。
 *
 * tag 为 DT_* 之一（见本文件定义），值可以是地址、大小或标志。
 * TCC 由 fill_dynamic() 生成：DT_HASH/DT_STRTAB/DT_SYMTAB/DT_STRSZ/DT_SYMENT 描述
 * 动态符号表与字符串表，DT_RELA(或 DT_REL)/DT_RELASZ/DT_RELAENT 描述重定位表，
 * DT_JMPREL/DT_PLTRELSZ/DT_PLTREL 描述 PLT 重定位，最后以 DT_NULL 结束。
 * 动态链接器按 tag 顺序读取这张表完成符号绑定与重定位。  */

typedef struct
{
  Elf32_Sword	d_tag;			/* 动态条目类型 */
  union
    {
      Elf32_Word d_val;			/* 整数值 */
      Elf32_Addr d_ptr;			/* 地址值 */
    } d_un;
} Elf32_Dyn;

typedef struct
{
  Elf64_Sxword	d_tag;			/* 动态条目类型 */
  union
    {
      Elf64_Xword d_val;		/* 整数值 */
      Elf64_Addr d_ptr;			/* 地址值 */
    } d_un;
} Elf64_Dyn;

/* d_tag（动态条目类型）的合法值。  */

#define DT_NULL		0		/* 标记动态段的结束 */
#define DT_NEEDED	1		/* 所需库的名称 */
#define DT_PLTRELSZ	2		/* PLT 重定位的大小（字节） */
#define DT_PLTGOT	3		/* 处理器定义的值 */
#define DT_HASH		4		/* 符号哈希表的地址 */
#define DT_STRTAB	5		/* 字符串表的地址 */
#define DT_SYMTAB	6		/* 符号表的地址 */
#define DT_RELA		7		/* Rela 重定位的地址 */
#define DT_RELASZ	8		/* Rela 重定位的总大小 */
#define DT_RELAENT	9		/* 一个 Rela 重定位的大小 */
#define DT_STRSZ	10		/* 字符串表的大小 */
#define DT_SYMENT	11		/* 一个符号表条目的大小 */
#define DT_INIT		12		/* init 函数的地址 */
#define DT_FINI		13		/* 终止函数的地址 */
#define DT_SONAME	14		/* 共享对象的名称 */
#define DT_RPATH	15		/* 库搜索路径（已废弃） */
#define DT_SYMBOLIC	16		/* 从此处开始搜索符号 */
#define DT_REL		17		/* Rel 重定位的地址 */
#define DT_RELSZ	18		/* Rel 重定位的总大小 */
#define DT_RELENT	19		/* 一个 Rel 重定位的大小 */
#define DT_PLTREL	20		/* PLT 中重定位的类型 */
#define DT_DEBUG	21		/* 用于调试；未指定 */
#define DT_TEXTREL	22		/* 重定位可能修改 .text */
#define DT_JMPREL	23		/* PLT 重定位的地址 */
#define	DT_BIND_NOW	24		/* 处理目标文件的重定位 */
#define	DT_INIT_ARRAY	25		/* 含 init 函数地址的数组 */
#define	DT_FINI_ARRAY	26		/* 含 fini 函数地址的数组 */
#define	DT_INIT_ARRAYSZ	27		/* DT_INIT_ARRAY 的大小（字节） */
#define	DT_FINI_ARRAYSZ	28		/* DT_FINI_ARRAY 的大小（字节） */
#define DT_RUNPATH	29		/* 库搜索路径 */
#define DT_FLAGS	30		/* 正在加载的目标文件的标志 */
#define DT_ENCODING	32		/* 编码范围的起始 */
#define DT_PREINIT_ARRAY 32		/* 含 preinit 函数地址的数组*/
#define DT_PREINIT_ARRAYSZ 33		/* DT_PREINIT_ARRAY 的大小（字节） */
#define	DT_NUM		34		/* 使用的数量 */
#define DT_LOOS		0x6000000d	/* OS 特定的起始 */
#define DT_HIOS		0x6ffff000	/* OS 特定的结束 */
#define DT_LOPROC	0x70000000	/* 处理器特定的起始 */
#define DT_HIPROC	0x7fffffff	/* 处理器特定的结束 */
#define	DT_PROCNUM	DT_MIPS_NUM	/* 任何处理器使用最多的数量 */

/* 落在 DT_VALRNGHI 与 DT_VALRNGLO 之间的 DT_* 条目使用 Elf*_Dyn 结构体的
   Dyn.d_un.d_val 字段。这遵循 Sun 的 做法。
  */
#define DT_VALRNGLO	0x6ffffd00
#define DT_GNU_PRELINKED 0x6ffffdf5	/* 预链接时间戳 */
#define DT_GNU_CONFLICTSZ 0x6ffffdf6	/* 冲突段的大小 */
#define DT_GNU_LIBLISTSZ 0x6ffffdf7	/* 库列表的大小 */
#define DT_CHECKSUM	0x6ffffdf8
#define DT_PLTPADSZ	0x6ffffdf9
#define DT_MOVEENT	0x6ffffdfa
#define DT_MOVESZ	0x6ffffdfb
#define DT_FEATURE_1	0x6ffffdfc	/* 特性选择（DTF_*）。  */
#define DT_POSFLAG_1	0x6ffffdfd	/* DT_* 条目的标志，影响 随后的 DT_* 条目。
  */
#define DT_SYMINSZ	0x6ffffdfe	/* syminfo 表的大小（字节） */
#define DT_SYMINENT	0x6ffffdff	/* syminfo 的条目大小 */
#define DT_VALRNGHI	0x6ffffdff
#define DT_VALTAGIDX(tag)	(DT_VALRNGHI - (tag))	/* 顺序相反！ */
#define DT_VALNUM 12

/* 落在 DT_ADDRRNGHI 与 DT_ADDRRNGLO 之间的 DT_* 条目使用 Elf*_Dyn 结构体的
   Dyn.d_un.d_ptr 字段。 如果 ELF 目标文件构建后做了任何调整， 这些条目将需要调整。


  */
#define DT_ADDRRNGLO	0x6ffffe00
#define DT_GNU_HASH	0x6ffffef5	/* GNU 风格的哈希表。  */
#define DT_TLSDESC_PLT	0x6ffffef6
#define DT_TLSDESC_GOT	0x6ffffef7
#define DT_GNU_CONFLICT	0x6ffffef8	/* 冲突段的起始 */
#define DT_GNU_LIBLIST	0x6ffffef9	/* 库列表 */
#define DT_CONFIG	0x6ffffefa	/* 配置信息。  */
#define DT_DEPAUDIT	0x6ffffefb	/* 依赖审计。  */
#define DT_AUDIT	0x6ffffefc	/* 对象审计。  */
#define	DT_PLTPAD	0x6ffffefd	/* PLT 填充。  */
#define	DT_MOVETAB	0x6ffffefe	/* Move 表。  */
#define DT_SYMINFO	0x6ffffeff	/* Syminfo 表。  */
#define DT_ADDRRNGHI	0x6ffffeff
#define DT_ADDRTAGIDX(tag)	(DT_ADDRRNGHI - (tag))	/* 顺序相反！ */
#define DT_ADDRNUM 11

/* 版本控制条目类型。 以下定义为 GNU 扩展的一部分。
  */
#define DT_VERSYM	0x6ffffff0

#define DT_RELACOUNT	0x6ffffff9
#define DT_RELCOUNT	0x6ffffffa

/* 这些由 Sun 选定。  */
#define DT_FLAGS_1	0x6ffffffb	/* 状态标志，见下文 DF_1_*。  */
#define	DT_VERDEF	0x6ffffffc	/* 版本定义表的 地址
 */
#define	DT_VERDEFNUM	0x6ffffffd	/* 版本定义计数 */
#define	DT_VERNEED	0x6ffffffe	/* 所需版本表的 地址
 */
#define	DT_VERNEEDNUM	0x6fffffff	/* 所需版本计数 */
#define DT_VERSIONTAGIDX(tag)	(DT_VERNEEDNUM - (tag))	/* 顺序相反！ */
#define DT_VERSIONTAGNUM 16

/* Sun 在 "processor-specific" 范围内加入这些机器无关扩展。保持兼容。
  */
#define DT_AUXILIARY    0x7ffffffd      /* 在自身之前加载的共享目标文件 */
#define DT_FILTER       0x7fffffff      /* 从中取值的共享目标文件 */
#define DT_EXTRATAGIDX(tag)	((Elf32_Word)-((Elf32_Sword) (tag) <<1>>1)-1)
#define DT_EXTRANUM	3

/* DT_FLAGS 条目中 `d_un.d_val' 的值。  */
#define DF_ORIGIN	0x00000001	/* 对象可使用 DF_ORIGIN */
#define DF_SYMBOLIC	0x00000002	/* 符号解析从此开始 */
#define DF_TEXTREL	0x00000004	/* 对象包含代码重定位 */
#define DF_BIND_NOW	0x00000008	/* 此对象不做延迟绑定 */
#define DF_STATIC_TLS	0x00000010	/* 模块使用静态 TLS 模型 */

/* 动态段中 DT_FLAGS_1 条目 `d_un.d_val' 元素可选的状态标志。
  */
#define DF_1_NOW	0x00000001	/* 为此对象设置 RTLD_NOW。  */
#define DF_1_GLOBAL	0x00000002	/* 为此对象设置 RTLD_GLOBAL。  */
#define DF_1_GROUP	0x00000004	/* 为此对象设置 RTLD_GROUP。  */
#define DF_1_NODELETE	0x00000008	/* 为此对象设置 RTLD_NODELETE。*/
#define DF_1_LOADFLTR	0x00000010	/* 在运行时触发 filtee 加载。*/
#define DF_1_INITFIRST	0x00000020	/* 为此对象设置 RTLD_INITFIRST*/
#define DF_1_NOOPEN	0x00000040	/* 为此对象设置 RTLD_NOOPEN。  */
#define DF_1_ORIGIN	0x00000080	/* $ORIGIN 必须处理。  */
#define DF_1_DIRECT	0x00000100	/* 已启用直接绑定。  */
#define DF_1_TRANS	0x00000200
#define DF_1_INTERPOSE	0x00000400	/* 对象用于介入。  */
#define DF_1_NODEFLIB	0x00000800	/* 忽略默认库搜索路径。  */
#define DF_1_NODUMP	0x00001000	/* 对象无法 dldump。  */
#define DF_1_CONFALT	0x00002000	/* 已创建配置替代项。*/
#define DF_1_ENDFILTEE	0x00004000	/* Filtee 终止过滤器搜索。 */
#define	DF_1_DISPRELDNE	0x00008000	/* Disp 重定位在构建时应用。 */
#define	DF_1_DISPRELPND	0x00010000	/* Disp 重定位在运行时应用。  */
#define	DF_1_NODIRECT	0x00020000	/* 对象为无直接绑定。 */
#define	DF_1_IGNMULDEF	0x00040000
#define	DF_1_NOKSYMS	0x00080000
#define	DF_1_NOHDR	0x00100000
#define	DF_1_EDITED	0x00200000	/* 对象在构建后被修改。  */
#define	DF_1_NORELOC	0x00400000
#define	DF_1_SYMINTPOSE	0x00800000	/* 对象有各自的介入者。  */
#define	DF_1_GLOBAUDIT	0x01000000	/* 需要全局审计。  */
#define	DF_1_SINGLETON	0x02000000	/* 使用了单例符号。  */

/* DT_FEATURE_1 中特性选择的标志。  */
#define DTF_1_PARINIT	0x00000001
#define DTF_1_CONFEXP	0x00000002

/* DT_POSFLAG_1 条目中仅影响下一个 DT_* 条目的标志。  */
#define DF_P1_LAZYLOAD	0x00000001	/* 延迟加载后续对象。  */
#define DF_P1_GROUPPERM	0x00000002	/* 下一个对象中的符号 通常不可用。
  */

/* 版本定义段。  */

typedef struct
{
  Elf32_Half	vd_version;		/* 版本修订号 */
  Elf32_Half	vd_flags;		/* 版本信息 */
  Elf32_Half	vd_ndx;			/* 版本索引 */
  Elf32_Half	vd_cnt;			/* 关联辅助条目计数 */
  Elf32_Word	vd_hash;		/* 版本名哈希值 */
  Elf32_Word	vd_aux;			/* 到 verdaux 数组的字节偏移 */
  Elf32_Word	vd_next;		/* 到下一个 verdef 条目的 字节偏移
 */
} Elf32_Verdef;

typedef struct
{
  Elf64_Half	vd_version;		/* 版本修订号 */
  Elf64_Half	vd_flags;		/* 版本信息 */
  Elf64_Half	vd_ndx;			/* 版本索引 */
  Elf64_Half	vd_cnt;			/* 关联辅助条目计数 */
  Elf64_Word	vd_hash;		/* 版本名哈希值 */
  Elf64_Word	vd_aux;			/* 到 verdaux 数组的字节偏移 */
  Elf64_Word	vd_next;		/* 到下一个 verdef 条目的 字节偏移
 */
} Elf64_Verdef;


/* vd_version（版本修订号）的合法值。  */
#define VER_DEF_NONE	0		/* 无版本 */
#define VER_DEF_CURRENT	1		/* 当前版本 */
#define VER_DEF_NUM	2		/* 给定版本号 */

/* vd_flags（版本信息标志）的合法值。  */
#define VER_FLG_BASE	0x1		/* 文件自身的版本定义 */
#define VER_FLG_WEAK	0x2		/* 弱版本标识符 */

/* Versym 符号索引值。  */
#define	VER_NDX_LOCAL		0	/* 符号为局部。  */
#define	VER_NDX_GLOBAL		1	/* 符号为全局。  */
#define	VER_NDX_LORESERVE	0xff00	/* 保留条目的起点。  */
#define	VER_NDX_ELIMINATE	0xff01	/* 符号将被消除。  */

/* 辅助版本信息。  */

typedef struct
{
  Elf32_Word	vda_name;		/* 版本名或依赖名 */
  Elf32_Word	vda_next;		/* 到下一个 verdaux 条目的 字节偏移
 */
} Elf32_Verdaux;

typedef struct
{
  Elf64_Word	vda_name;		/* 版本名或依赖名 */
  Elf64_Word	vda_next;		/* 到下一个 verdaux 条目的 字节偏移
 */
} Elf64_Verdaux;


/* 版本依赖段。  */

typedef struct
{
  Elf32_Half	vn_version;		/* 结构的版本 */
  Elf32_Half	vn_cnt;			/* 关联辅助条目计数 */
  Elf32_Word	vn_file;		/* 此依赖文件名的 偏移
 */
  Elf32_Word	vn_aux;			/* 到 vernaux 数组的字节偏移 */
  Elf32_Word	vn_next;		/* 到下一个 verneed 条目的 字节偏移
 */
} Elf32_Verneed;

typedef struct
{
  Elf64_Half	vn_version;		/* 结构的版本 */
  Elf64_Half	vn_cnt;			/* 关联辅助条目计数 */
  Elf64_Word	vn_file;		/* 此依赖文件名的 偏移
 */
  Elf64_Word	vn_aux;			/* 到 vernaux 数组的字节偏移 */
  Elf64_Word	vn_next;		/* 到下一个 verneed 条目的 字节偏移
 */
} Elf64_Verneed;


/* vn_version（版本修订号）的合法值。  */
#define VER_NEED_NONE	 0		/* 无版本 */
#define VER_NEED_CURRENT 1		/* 当前版本 */
#define VER_NEED_NUM	 2		/* 给定版本号 */

/* 辅助所需版本信息。  */

typedef struct
{
  Elf32_Word	vna_hash;		/* 依赖名的哈希值 */
  Elf32_Half	vna_flags;		/* 依赖特定信息 */
  Elf32_Half	vna_other;		/* 未使用 */
  Elf32_Word	vna_name;		/* 依赖名字符串偏移 */
  Elf32_Word	vna_next;		/* 到下一个 vernaux 条目的 字节偏移
 */
} Elf32_Vernaux;

typedef struct
{
  Elf64_Word	vna_hash;		/* 依赖名的哈希值 */
  Elf64_Half	vna_flags;		/* 依赖特定信息 */
  Elf64_Half	vna_other;		/* 未使用 */
  Elf64_Word	vna_name;		/* 依赖名字符串偏移 */
  Elf64_Word	vna_next;		/* 到下一个 vernaux 条目的 字节偏移
 */
} Elf64_Vernaux;


/* vna_flags 的合法值。  */
#define VER_FLG_WEAK	0x2		/* 弱版本标识符 */


/* 辅助向量。  */

/* 此向量通常只由程序解释器使用。 ABI 附录中的通常定义使用名称 auxv_t。
   此向量通常不定义在标准 <elf.h> 文件中，但 定义也无妨。我们重命名以避免冲突。这些
   类型的大小是 exec 服务器与程序 解释器之间的约定，因此此处不作完整规定。


  */

typedef struct
{
  uint32_t a_type;		/* 条目类型 */
  union
    {
      uint32_t a_val;		/* 整数值 */
      /* 我们曾在此加入指针元素。但 不能这样做，因为 32 位定义 用在 64
	 位平台上会失效，反之亦然。
  */
    } a_un;
} Elf32_auxv_t;

typedef struct
{
  uint64_t a_type;		/* 条目类型 */
  union
    {
      uint64_t a_val;		/* 整数值 */
      /* 我们曾在此加入指针元素。但 不能这样做，因为 32 位定义 用在 64
	 位平台上会失效，反之亦然。
  */
    } a_un;
} Elf64_auxv_t;

/* a_type（条目类型）的合法值。  */

#define AT_NULL		0		/* 向量结尾 */
#define AT_IGNORE	1		/* 条目应被忽略 */
#define AT_EXECFD	2		/* 程序的文件描述符 */
#define AT_PHDR		3		/* 程序的程序头 */
#define AT_PHENT	4		/* 程序头条目的大小 */
#define AT_PHNUM	5		/* 程序头计数 */
#define AT_PAGESZ	6		/* 系统页大小 */
#define AT_BASE		7		/* 解释器的基地址 */
#define AT_FLAGS	8		/* 标志 */
#define AT_ENTRY	9		/* 程序入口点 */
#define AT_NOTELF	10		/* 程序不是 ELF */
#define AT_UID		11		/* 真实 uid */
#define AT_EUID		12		/* 有效 uid */
#define AT_GID		13		/* 真实 gid */
#define AT_EGID		14		/* 有效 gid */
#define AT_CLKTCK	17		/* times() 的频率 */

/* 更多描述硬件的特殊 a_type 值。  */
#define AT_PLATFORM	15		/* 标识平台的字符串。  */
#define AT_HWCAP	16		/* 关于处理器能力的 机器相关提示。
  */

/* 此条目给出内核执行的 FPU 初始化的部分信息。
  */
#define AT_FPUCW	18		/* 使用的 FPU 控制字。  */

/* 缓存块大小。  */
#define AT_DCACHEBSIZE	19		/* 数据缓存块大小。  */
#define AT_ICACHEBSIZE	20		/* 指令缓存块大小。  */
#define AT_UCACHEBSIZE	21		/* 统一缓存块大小。  */

/* PPC 的特殊忽略值，内核用它控制 AUXV 的解释。必须 > 16。
  */
#define AT_IGNOREPPC	22		/* 条目应被忽略。  */

#define	AT_SECURE	23		/* 布尔值，exec 是否类似 setuid？  */

#define AT_BASE_PLATFORM 24		/* 标识真实平台的字符串。*/

#define AT_RANDOM	25		/* 16 个随机字节的地址。  */

#define AT_EXECFN	31		/* 可执行文件的文件名。  */

/* 指向用于系统调用及其他好东西的 全局系统页的指针。
  */
#define AT_SYSINFO	32
#define AT_SYSINFO_EHDR	33

/* 缓存的形态。位 0-3 含相联度；位 4-7 含 行大小的 log2；掩码取出它们即得缓存大小。
  */
#define AT_L1I_CACHESHAPE	34
#define AT_L1D_CACHESHAPE	35
#define AT_L2_CACHESHAPE	36
#define AT_L3_CACHESHAPE	37

/* Note 段内容。Note 段中每个条目以 固定形式的头开始。
  */

typedef struct
{
  Elf32_Word n_namesz;			/* note 名的大小。  */
  Elf32_Word n_descsz;			/* note 描述符的大小。  */
  Elf32_Word n_type;			/* note 的类型。  */
} Elf32_Nhdr;

typedef struct
{
  Elf64_Word n_namesz;			/* note 名的大小。  */
  Elf64_Word n_descsz;			/* note 描述符的大小。  */
  Elf64_Word n_type;			/* note 的类型。  */
} Elf64_Nhdr;

/* 已知的 note 名。  */

/* note 段中 Solaris 条目使用此名称。  */
#define ELF_NOTE_SOLARIS	"SUNW Solaris"

/* GNU 系统的 note 条目使用此名称。  */
#define ELF_NOTE_GNU		"GNU"


/* Solaris 已定义的 note 类型。  */

/* 描述符的值（一个字）为二进制所需的页大小。  */
#define ELF_NOTE_PAGESIZE_HINT	1


/* GNU 系统已定义的 note 类型。  */

/* ABI 信息。描述符由以下字组成： 字 0：OS 描述符 字 1：ABI 的主版本号 字 2：ABI
   的次版本号 字 3：ABI 的次次版本号



*/
#define NT_GNU_ABI_TAG	1
#define ELF_NOTE_ABI	NT_GNU_ABI_TAG /* 旧名称。  */

/* 已知 OS。这些值可出现在 NT_GNU_ABI_TAG note 段条目的字 0 中。
  */
#define ELF_NOTE_OS_LINUX	0
#define ELF_NOTE_OS_GNU		1
#define ELF_NOTE_OS_SOLARIS2	2
#define ELF_NOTE_OS_FREEBSD	3

/* 合成的 hwcap 信息。描述符以两个字开始： 字 0：条目计数 字 1：已启用条目的位掩码
   随后是可变长度条目，一个字节后跟以 '\0' 结尾的 hwcap 名字符串。该字节给出
   要测试是否启用的位号，(1U << bit) & bitmask。


  */
#define NT_GNU_HWCAP	2

/* 由 ld --build-id 生成的 Build ID 位。 描述符由任意非零字节数组成。
  */
#define NT_GNU_BUILD_ID	3

/* GNU gold 生成的含版本字符串的版本 note。  */
#define NT_GNU_GOLD_VERSION	4


/* Move 记录。  */
typedef struct
{
  Elf32_Xword m_value;		/* 符号值。  */
  Elf32_Word m_info;		/* 大小与索引。  */
  Elf32_Word m_poffset;		/* 符号偏移。  */
  Elf32_Half m_repeat;		/* 重复计数。  */
  Elf32_Half m_stride;		/* 步长信息。  */
} Elf32_Move;

typedef struct
{
  Elf64_Xword m_value;		/* 符号值。  */
  Elf64_Xword m_info;		/* 大小与索引。  */
  Elf64_Xword m_poffset;	/* 符号偏移。  */
  Elf64_Half m_repeat;		/* 重复计数。  */
  Elf64_Half m_stride;		/* 步长信息。  */
} Elf64_Move;

/* 构造 move 记录的宏。  */
#define ELF32_M_SYM(info)	((info) >> 8)
#define ELF32_M_SIZE(info)	((unsigned char) (info))
#define ELF32_M_INFO(sym, size)	(((sym) << 8) + (unsigned char) (size))

#define ELF64_M_SYM(info)	ELF32_M_SYM (info)
#define ELF64_M_SIZE(info)	ELF32_M_SIZE (info)
#define ELF64_M_INFO(sym, size)	ELF32_M_INFO (sym, size)


/* Motorola 68k 特定定义。  */

/* Elf32_Ehdr.e_flags 的值。  */
#define EF_CPU32	0x00810000

/* m68k 重定位。  */

#define R_68K_NONE	0		/* 无重定位 */
#define R_68K_32	1		/* 直接 32 位  */
#define R_68K_16	2		/* 直接 16 位  */
#define R_68K_8		3		/* 直接 8 位  */
#define R_68K_PC32	4		/* PC 相对 32 位 */
#define R_68K_PC16	5		/* PC 相对 16 位 */
#define R_68K_PC8	6		/* PC 相对 8 位 */
#define R_68K_GOT32	7		/* 32 位 PC 相对 GOT 条目 */
#define R_68K_GOT16	8		/* 16 位 PC 相对 GOT 条目 */
#define R_68K_GOT8	9		/* 8 位 PC 相对 GOT 条目 */
#define R_68K_GOT32O	10		/* 32 位 GOT 偏移 */
#define R_68K_GOT16O	11		/* 16 位 GOT 偏移 */
#define R_68K_GOT8O	12		/* 8 位 GOT 偏移 */
#define R_68K_PLT32	13		/* 32 位 PC 相对 PLT 地址 */
#define R_68K_PLT16	14		/* 16 位 PC 相对 PLT 地址 */
#define R_68K_PLT8	15		/* 8 位 PC 相对 PLT 地址 */
#define R_68K_PLT32O	16		/* 32 位 PLT 偏移 */
#define R_68K_PLT16O	17		/* 16 位 PLT 偏移 */
#define R_68K_PLT8O	18		/* 8 位 PLT 偏移 */
#define R_68K_COPY	19		/* 运行时复制符号 */
#define R_68K_GLOB_DAT	20		/* 创建 GOT 条目 */
#define R_68K_JMP_SLOT	21		/* 创建 PLT 条目 */
#define R_68K_RELATIVE	22		/* 按程序基址调整 */
#define R_68K_TLS_GD32      25          /* GD 的 32 位 GOT 偏移 */
#define R_68K_TLS_GD16      26          /* GD 的 16 位 GOT 偏移 */
#define R_68K_TLS_GD8       27          /* GD 的 8 位 GOT 偏移 */
#define R_68K_TLS_LDM32     28          /* LDM 的 32 位 GOT 偏移 */
#define R_68K_TLS_LDM16     29          /* LDM 的 16 位 GOT 偏移 */
#define R_68K_TLS_LDM8      30          /* LDM 的 8 位 GOT 偏移 */
#define R_68K_TLS_LDO32     31          /* 32 位模块相对偏移 */
#define R_68K_TLS_LDO16     32          /* 16 位模块相对偏移 */
#define R_68K_TLS_LDO8      33          /* 8 位模块相对偏移 */
#define R_68K_TLS_IE32      34          /* IE 的 32 位 GOT 偏移 */
#define R_68K_TLS_IE16      35          /* IE 的 16 位 GOT 偏移 */
#define R_68K_TLS_IE8       36          /* IE 的 8 位 GOT 偏移 */
#define R_68K_TLS_LE32      37          /* 相对于静态 TLS 块的 32 位偏移
 */
#define R_68K_TLS_LE16      38          /* 相对于静态 TLS 块的 16 位偏移
 */
#define R_68K_TLS_LE8       39          /* 相对于静态 TLS 块的 8 位偏移
 */
#define R_68K_TLS_DTPMOD32  40          /* 32 位模块号 */
#define R_68K_TLS_DTPREL32  41          /* 32 位模块相对偏移 */
#define R_68K_TLS_TPREL32   42          /* 32 位 TP 相对偏移 */
/* 保持此条目为最后一项。  */
#define R_68K_NUM	43

/* Intel 80386 特定定义。  */

/* i386 重定位。  */

#define R_386_NONE	   0		/* 无重定位 */
#define R_386_32	   1		/* 直接 32 位  */
#define R_386_PC32	   2		/* PC 相对 32 位 */
#define R_386_GOT32	   3		/* 32 位 GOT 条目 */
#define R_386_PLT32	   4		/* 32 位 PLT 地址 */
#define R_386_COPY	   5		/* 运行时复制符号 */
#define R_386_GLOB_DAT	   6		/* 创建 GOT 条目 */
#define R_386_JMP_SLOT	   7		/* 创建 PLT 条目 */
#define R_386_RELATIVE	   8		/* 按程序基址调整 */
#define R_386_GOTOFF	   9		/* 到 GOT 的 32 位偏移 */
#define R_386_GOTPC	   10		/* 到 GOT 的 32 位 PC 相对偏移 */
#define R_386_32PLT	   11
#define R_386_TLS_TPOFF	   14		/* 静态 TLS 块中的偏移 */
#define R_386_TLS_IE	   15		/* 静态 TLS 块偏移的 GOT 条目的地址
 */
#define R_386_TLS_GOTIE	   16		/* 静态 TLS 块偏移的 GOT 条目
 */
#define R_386_TLS_LE	   17		/* 相对于静态 TLS 块的 偏移
 */
#define R_386_TLS_GD	   18		/* GNU 版通用动态线程局部数据的 直接 32 位
 */
#define R_386_TLS_LDM	   19		/* LE 代码中 GNU 版本地动态 线程局部数据的 直接 32 位

 */
#define R_386_16	   20
#define R_386_PC16	   21
#define R_386_8		   22
#define R_386_PC8	   23
#define R_386_TLS_GD_32	   24		/* 通用动态线程局部数据的 直接 32 位
 */
#define R_386_TLS_GD_PUSH  25		/* GD TLS 代码中 pushl 的标记 */
#define R_386_TLS_GD_CALL  26		/* 调用 __tls_get_addr() 的 重定位
 */
#define R_386_TLS_GD_POP   27		/* GD TLS 代码中 popl 的标记 */
#define R_386_TLS_LDM_32   28		/* LE 代码中本地动态线程局部 数据的直接 32 位
 */
#define R_386_TLS_LDM_PUSH 29		/* LDM TLS 代码中 pushl 的标记 */
#define R_386_TLS_LDM_CALL 30		/* LDM 代码中调用 __tls_get_addr() 的重定位
 */
#define R_386_TLS_LDM_POP  31		/* LDM TLS 代码中 popl 的标记 */
#define R_386_TLS_LDO_32   32		/* 相对于 TLS 块的偏移 */
#define R_386_TLS_IE_32	   33		/* 取反的静态 TLS 块偏移的 GOT 条目
 */
#define R_386_TLS_LE_32	   34		/* 相对于静态 TLS 块的 取反偏移
 */
#define R_386_TLS_DTPMOD32 35		/* 含符号的模块的 ID */
#define R_386_TLS_DTPOFF32 36		/* TLS 块中的偏移 */
#define R_386_TLS_TPOFF32  37		/* 静态 TLS 块中的取反偏移 */
/* 38? */
#define R_386_TLS_GOTDESC  39		/* TLS 描述符的 GOT 偏移。  */
#define R_386_TLS_DESC_CALL 40		/* 通过 TLS 描述符调用以 进行松弛的 标记。

  */
#define R_386_TLS_DESC     41		/* TLS 描述符，含指向 代码和参数的指针， 返回该符号的 TLS 偏移。


  */
#define R_386_IRELATIVE	   42		/* 按程序基址间接调整 */
#define R_386_GOT32X       43		/* 32 位 GOT 条目，可松弛 */
/* 保持此条目为最后一项。  */
#define R_386_NUM	   44

/* SUN SPARC 特定定义。  */

/* st_info 的 ST_TYPE 子字段（符号类型）的合法值。  */

#define STT_SPARC_REGISTER	13	/* 保留给应用的全局寄存器。 */

/* Elf64_Ehdr.e_flags 的值。  */

#define EF_SPARCV9_MM		3
#define EF_SPARCV9_TSO		0
#define EF_SPARCV9_PSO		1
#define EF_SPARCV9_RMO		2
#define EF_SPARC_LEDATA		0x800000 /* 小端数据 */
#define EF_SPARC_EXT_MASK	0xFFFF00
#define EF_SPARC_32PLUS		0x000100 /* 通用 V8+ 特性 */
#define EF_SPARC_SUN_US1	0x000200 /* Sun UltraSPARC1 扩展 */
#define EF_SPARC_HAL_R1		0x000400 /* HAL R1 扩展 */
#define EF_SPARC_SUN_US3	0x000800 /* Sun UltraSPARCIII 扩展 */

/* SPARC 重定位。  */

#define R_SPARC_NONE		0	/* 无重定位 */
#define R_SPARC_8		1	/* 直接 8 位 */
#define R_SPARC_16		2	/* 直接 16 位 */
#define R_SPARC_32		3	/* 直接 32 位 */
#define R_SPARC_DISP8		4	/* PC 相对 8 位 */
#define R_SPARC_DISP16		5	/* PC 相对 16 位 */
#define R_SPARC_DISP32		6	/* PC 相对 32 位 */
#define R_SPARC_WDISP30		7	/* PC 相对 30 位左移 */
#define R_SPARC_WDISP22		8	/* PC 相对 22 位左移 */
#define R_SPARC_HI22		9	/* 高 22 位 */
#define R_SPARC_22		10	/* 直接 22 位 */
#define R_SPARC_13		11	/* 直接 13 位 */
#define R_SPARC_LO10		12	/* 截断的 10 位 */
#define R_SPARC_GOT10		13	/* 截断的 10 位 GOT 条目 */
#define R_SPARC_GOT13		14	/* 13 位 GOT 条目 */
#define R_SPARC_GOT22		15	/* 22 位 GOT 条目左移 */
#define R_SPARC_PC10		16	/* PC 相对 10 位截断 */
#define R_SPARC_PC22		17	/* PC 相对 22 位左移 */
#define R_SPARC_WPLT30		18	/* 30 位 PC 相对 PLT 地址 */
#define R_SPARC_COPY		19	/* 运行时复制符号 */
#define R_SPARC_GLOB_DAT	20	/* 创建 GOT 条目 */
#define R_SPARC_JMP_SLOT	21	/* 创建 PLT 条目 */
#define R_SPARC_RELATIVE	22	/* 按程序基址调整 */
#define R_SPARC_UA32		23	/* 直接 32 位非对齐 */

/* 附加 Sparc64 重定位。  */

#define R_SPARC_PLT32		24	/* 对 PLT 条目的直接 32 位引用 */
#define R_SPARC_HIPLT22		25	/* 高 22 位 PLT 条目 */
#define R_SPARC_LOPLT10		26	/* 截断的 10 位 PLT 条目 */
#define R_SPARC_PCPLT32		27	/* 对 PLT 条目的 PC 相对 32 位引用 */
#define R_SPARC_PCPLT22		28	/* PC 相对高 22 位 PLT 条目 */
#define R_SPARC_PCPLT10		29	/* PC 相对截断 10 位 PLT 条目 */
#define R_SPARC_10		30	/* 直接 10 位 */
#define R_SPARC_11		31	/* 直接 11 位 */
#define R_SPARC_64		32	/* 直接 64 位 */
#define R_SPARC_OLO10		33	/* 带次级 13 位加数的 10 位 */
#define R_SPARC_HH22		34	/* 直接 64 位的高 22 位 */
#define R_SPARC_HM10		35	/* ... 的高中间 10 位 */
#define R_SPARC_LM22		36	/* ... 的低中间 22 位 */
#define R_SPARC_PC_HH22		37	/* PC 相对 64 位的高 22 位 */
#define R_SPARC_PC_HM10		38	/* ... 的高中间 10 位 */
#define R_SPARC_PC_LM22		39	/* ... 的低中间 22 位 */
#define R_SPARC_WDISP16		40	/* PC 相对 16 位左移 */
#define R_SPARC_WDISP19		41	/* PC 相对 19 位左移 */
#define R_SPARC_GLOB_JMP	42	/* 曾是 v9 ABI 的一部分但已移除 */
#define R_SPARC_7		43	/* 直接 7 位 */
#define R_SPARC_5		44	/* 直接 5 位 */
#define R_SPARC_6		45	/* 直接 6 位 */
#define R_SPARC_DISP64		46	/* PC 相对 64 位 */
#define R_SPARC_PLT64		47	/* 对 PLT 条目的直接 64 位引用 */
#define R_SPARC_HIX22		48	/* 高 22 位取补 */
#define R_SPARC_LOX10		49	/* 截断的 11 位取补 */
#define R_SPARC_H44		50	/* 44 位中的直接高 12 位 */
#define R_SPARC_M44		51	/* 44 位中的直接中 22 位 */
#define R_SPARC_L44		52	/* 44 位中的直接低 10 位 */
#define R_SPARC_REGISTER	53	/* 全局寄存器使用 */
#define R_SPARC_UA64		54	/* 直接 64 位非对齐 */
#define R_SPARC_UA16		55	/* 直接 16 位非对齐 */
#define R_SPARC_TLS_GD_HI22	56
#define R_SPARC_TLS_GD_LO10	57
#define R_SPARC_TLS_GD_ADD	58
#define R_SPARC_TLS_GD_CALL	59
#define R_SPARC_TLS_LDM_HI22	60
#define R_SPARC_TLS_LDM_LO10	61
#define R_SPARC_TLS_LDM_ADD	62
#define R_SPARC_TLS_LDM_CALL	63
#define R_SPARC_TLS_LDO_HIX22	64
#define R_SPARC_TLS_LDO_LOX10	65
#define R_SPARC_TLS_LDO_ADD	66
#define R_SPARC_TLS_IE_HI22	67
#define R_SPARC_TLS_IE_LO10	68
#define R_SPARC_TLS_IE_LD	69
#define R_SPARC_TLS_IE_LDX	70
#define R_SPARC_TLS_IE_ADD	71
#define R_SPARC_TLS_LE_HIX22	72
#define R_SPARC_TLS_LE_LOX10	73
#define R_SPARC_TLS_DTPMOD32	74
#define R_SPARC_TLS_DTPMOD64	75
#define R_SPARC_TLS_DTPOFF32	76
#define R_SPARC_TLS_DTPOFF64	77
#define R_SPARC_TLS_TPOFF32	78
#define R_SPARC_TLS_TPOFF64	79
#define R_SPARC_GOTDATA_HIX22	80
#define R_SPARC_GOTDATA_LOX10	81
#define R_SPARC_GOTDATA_OP_HIX22	82
#define R_SPARC_GOTDATA_OP_LOX10	83
#define R_SPARC_GOTDATA_OP	84
#define R_SPARC_H34		85
#define R_SPARC_SIZE32		86
#define R_SPARC_SIZE64		87
#define R_SPARC_WDISP10		88
#define R_SPARC_JMP_IREL	248
#define R_SPARC_IRELATIVE	249
#define R_SPARC_GNU_VTINHERIT	250
#define R_SPARC_GNU_VTENTRY	251
#define R_SPARC_REV32		252
/* 保持此条目为最后一项。  */
#define R_SPARC_NUM		253

/* Sparc64 的 Elf64_Dyn 的 d_tag 合法值。  */

#define DT_SPARC_REGISTER 0x70000001
#define DT_SPARC_NUM	2

/* MIPS R3000 特定定义。  */

/* Elf32_Ehdr 的 e_flags 字段的合法值。  */

#define EF_MIPS_NOREORDER   1		/* 使用了 .noreorder 指示 */
#define EF_MIPS_PIC	    2		/* 包含 PIC 代码 */
#define EF_MIPS_CPIC	    4		/* 使用 PIC 调用序列 */
#define EF_MIPS_XGOT	    8
#define EF_MIPS_64BIT_WHIRL 16
#define EF_MIPS_ABI2	    32
#define EF_MIPS_ABI_ON32    64
#define EF_MIPS_ARCH	    0xf0000000	/* MIPS 体系结构级别 */

/* MIPS 体系结构级别的合法值。  */

#define EF_MIPS_ARCH_1	    0x00000000	/* -mips1 代码。  */
#define EF_MIPS_ARCH_2	    0x10000000	/* -mips2 代码。  */
#define EF_MIPS_ARCH_3	    0x20000000	/* -mips3 代码。  */
#define EF_MIPS_ARCH_4	    0x30000000	/* -mips4 代码。  */
#define EF_MIPS_ARCH_5	    0x40000000	/* -mips5 代码。  */
#define EF_MIPS_ARCH_32	    0x60000000	/* MIPS32 代码。  */
#define EF_MIPS_ARCH_64	    0x70000000	/* MIPS64 代码。  */

/* 以下为非官方名称，不应使用。  */

#define E_MIPS_ARCH_1	  0x00000000	/* -mips1 代码。  */
#define E_MIPS_ARCH_2	  0x10000000	/* -mips2 代码。  */
#define E_MIPS_ARCH_3	  0x20000000	/* -mips3 代码。  */
#define E_MIPS_ARCH_4	  0x30000000	/* -mips4 代码。  */
#define E_MIPS_ARCH_5	  0x40000000	/* -mips5 代码。  */
#define E_MIPS_ARCH_32	  0x60000000	/* MIPS32 代码。  */
#define E_MIPS_ARCH_64	  0x70000000	/* MIPS64 代码。  */

/* 特殊段索引。  */

#define SHN_MIPS_ACOMMON    0xff00	/* 已分配的公共符号 */
#define SHN_MIPS_TEXT	    0xff01	/* 已分配的测试符号。  */
#define SHN_MIPS_DATA	    0xff02	/* 已分配的数据符号。  */
#define SHN_MIPS_SCOMMON    0xff03	/* 小公共符号 */
#define SHN_MIPS_SUNDEFINED 0xff04	/* 小未定义符号 */

/* Elf32_Shdr 的 sh_type 字段的合法值。  */

#define SHT_MIPS_LIBLIST       0x70000000 /* 链接中使用的共享目标文件 */
#define SHT_MIPS_MSYM	       0x70000001
#define SHT_MIPS_CONFLICT      0x70000002 /* 冲突符号 */
#define SHT_MIPS_GPTAB	       0x70000003 /* 全局数据区大小 */
#define SHT_MIPS_UCODE	       0x70000004 /* 保留给 SGI/MIPS 编译器 */
#define SHT_MIPS_DEBUG	       0x70000005 /* MIPS ECOFF 调试信息*/
#define SHT_MIPS_REGINFO       0x70000006 /* 寄存器使用信息 */
#define SHT_MIPS_PACKAGE       0x70000007
#define SHT_MIPS_PACKSYM       0x70000008
#define SHT_MIPS_RELD	       0x70000009
#define SHT_MIPS_IFACE         0x7000000b
#define SHT_MIPS_CONTENT       0x7000000c
#define SHT_MIPS_OPTIONS       0x7000000d /* 杂项选项。  */
#define SHT_MIPS_SHDR	       0x70000010
#define SHT_MIPS_FDESC	       0x70000011
#define SHT_MIPS_EXTSYM	       0x70000012
#define SHT_MIPS_DENSE	       0x70000013
#define SHT_MIPS_PDESC	       0x70000014
#define SHT_MIPS_LOCSYM	       0x70000015
#define SHT_MIPS_AUXSYM	       0x70000016
#define SHT_MIPS_OPTSYM	       0x70000017
#define SHT_MIPS_LOCSTR	       0x70000018
#define SHT_MIPS_LINE	       0x70000019
#define SHT_MIPS_RFDESC	       0x7000001a
#define SHT_MIPS_DELTASYM      0x7000001b
#define SHT_MIPS_DELTAINST     0x7000001c
#define SHT_MIPS_DELTACLASS    0x7000001d
#define SHT_MIPS_DWARF         0x7000001e /* DWARF 调试信息。  */
#define SHT_MIPS_DELTADECL     0x7000001f
#define SHT_MIPS_SYMBOL_LIB    0x70000020
#define SHT_MIPS_EVENTS	       0x70000021 /* 事件段。  */
#define SHT_MIPS_TRANSLATE     0x70000022
#define SHT_MIPS_PIXIE	       0x70000023
#define SHT_MIPS_XLATE	       0x70000024
#define SHT_MIPS_XLATE_DEBUG   0x70000025
#define SHT_MIPS_WHIRL	       0x70000026
#define SHT_MIPS_EH_REGION     0x70000027
#define SHT_MIPS_XLATE_OLD     0x70000028
#define SHT_MIPS_PDR_EXCEPTION 0x70000029

/* Elf32_Shdr 的 sh_flags 字段的合法值。  */

#define SHF_MIPS_GPREL	 0x10000000	/* 必须是全局数据区的一部分 */
#define SHF_MIPS_MERGE	 0x20000000
#define SHF_MIPS_ADDR	 0x40000000
#define SHF_MIPS_STRINGS 0x80000000
#define SHF_MIPS_NOSTRIP 0x08000000
#define SHF_MIPS_LOCAL	 0x04000000
#define SHF_MIPS_NAMES	 0x02000000
#define SHF_MIPS_NODUPE	 0x01000000


/* 符号表。  */

/* `st_other' 的 MIPS 特定值。  */
#define STO_MIPS_DEFAULT		0x0
#define STO_MIPS_INTERNAL		0x1
#define STO_MIPS_HIDDEN			0x2
#define STO_MIPS_PROTECTED		0x3
#define STO_MIPS_PLT			0x8
#define STO_MIPS_SC_ALIGN_UNUSED	0xff

/* `st_info' 的 MIPS 特定值。  */
#define STB_MIPS_SPLIT_COMMON		13

/* SHT_MIPS_GPTAB 类型段中的条目。  */

typedef union
{
  struct
    {
      Elf32_Word gt_current_g_value;	/* 编译所用的 -G 值 */
      Elf32_Word gt_unused;		/* 未使用 */
    } gt_header;			/* 段中第一个条目 */
  struct
    {
      Elf32_Word gt_g_value;		/* 若此值用于 -G */
      Elf32_Word gt_bytes;		/* 将使用这么多字节 */
    } gt_entry;				/* 段中后续条目 */
} Elf32_gptab;

/* SHT_MIPS_REGINFO 类型段中的条目。  */

typedef struct
{
  Elf32_Word	ri_gprmask;		/* 使用的通用寄存器 */
  Elf32_Word	ri_cprmask[4];		/* 使用的协处理器寄存器 */
  Elf32_Sword	ri_gp_value;		/* $gp 寄存器值 */
} Elf32_RegInfo;

/* SHT_MIPS_OPTIONS 类型段中的条目。  */

typedef struct
{
  unsigned char kind;		/* 决定描述符可变部分的 解释方式。
  */
  unsigned char size;		/* 描述符的大小，含头。  */
  Elf32_Section section;	/* 受影响段的段头索引， 全局选项为 0。
  */
  Elf32_Word info;		/* 类型特定信息。  */
} Elf_Options;

/* Elf_Options 中 `kind' 字段的值。  */

#define ODK_NULL	0	/* 未定义。  */
#define ODK_REGINFO	1	/* 寄存器使用信息。  */
#define ODK_EXCEPTIONS	2	/* 异常处理选项。  */
#define ODK_PAD		3	/* 段填充选项。  */
#define ODK_HWPATCH	4	/* 已执行的硬件变通 */
#define ODK_FILL	5	/* 记录链接器使用的填充值。 */
#define ODK_TAGS	6	/* 为桌面工具写入保留空间。 */
#define ODK_HWAND	7	/* 硬件变通。合并时按位 'AND'。 */
#define ODK_HWOR	8	/* 硬件变通。合并时按位 'OR'。  */

/* ODK_EXCEPTIONS 条目的 Elf_Options 中 `info' 的值。  */

#define OEX_FPU_MIN	0x1f	/* 必须启用的 FPE。  */
#define OEX_FPU_MAX	0x1f00	/* 可以启用的 FPE。  */
#define OEX_PAGE0	0x10000	/* 页零必须映射。  */
#define OEX_SMM		0x20000	/* 强制顺序内存模式？  */
#define OEX_FPDBUG	0x40000	/* 强制浮点调试模式？  */
#define OEX_PRECISEFP	OEX_FPDBUG
#define OEX_DISMISS	0x80000	/* 忽略无效地址错误？  */

#define OEX_FPU_INVAL	0x10
#define OEX_FPU_DIV0	0x08
#define OEX_FPU_OFLO	0x04
#define OEX_FPU_UFLO	0x02
#define OEX_FPU_INEX	0x01

/* ODK_HWPATCH 条目的 Elf_Options 中 `info' 的掩码。  */

#define OHW_R4KEOP	0x1	/* R4000 页末补丁。  */
#define OHW_R8KPFETCH	0x2	/* 可能需要 R8000 预取补丁。  */
#define OHW_R5KEOP	0x4	/* R5000 页末补丁。  */
#define OHW_R5KCVTL	0x8	/* R5000 cvt.[ds].l 缺陷。clean=1。  */

#define OPAD_PREFIX	0x1
#define OPAD_POSTFIX	0x2
#define OPAD_SYMBOL	0x4

/* `.options' 段中的条目。  */

typedef struct
{
  Elf32_Word hwp_flags1;	/* 额外标志。  */
  Elf32_Word hwp_flags2;	/* 额外标志。  */
} Elf_Options_Hw;

/* ODK_HWAND 和 ODK_HWOR 条目的 ElfOptions 中 `info' 的掩码。  */

#define OHWA0_R4KEOP_CHECKED	0x00000001
#define OHWA1_R4KEOP_CLEAN	0x00000002

/* MIPS 重定位。  */

#define R_MIPS_NONE		0	/* 无重定位 */
#define R_MIPS_16		1	/* 直接 16 位 */
#define R_MIPS_32		2	/* 直接 32 位 */
#define R_MIPS_REL32		3	/* PC 相对 32 位 */
#define R_MIPS_26		4	/* 直接 26 位左移 */
#define R_MIPS_HI16		5	/* 高 16 位 */
#define R_MIPS_LO16		6	/* 低 16 位 */
#define R_MIPS_GPREL16		7	/* GP 相对 16 位 */
#define R_MIPS_LITERAL		8	/* 16 位字面量条目 */
#define R_MIPS_GOT16		9	/* 16 位 GOT 条目 */
#define R_MIPS_PC16		10	/* PC 相对 16 位 */
#define R_MIPS_CALL16		11	/* 函数的 16 位 GOT 条目 */
#define R_MIPS_GPREL32		12	/* GP 相对 32 位 */

#define R_MIPS_SHIFT5		16
#define R_MIPS_SHIFT6		17
#define R_MIPS_64		18
#define R_MIPS_GOT_DISP		19
#define R_MIPS_GOT_PAGE		20
#define R_MIPS_GOT_OFST		21
#define R_MIPS_GOT_HI16		22
#define R_MIPS_GOT_LO16		23
#define R_MIPS_SUB		24
#define R_MIPS_INSERT_A		25
#define R_MIPS_INSERT_B		26
#define R_MIPS_DELETE		27
#define R_MIPS_HIGHER		28
#define R_MIPS_HIGHEST		29
#define R_MIPS_CALL_HI16	30
#define R_MIPS_CALL_LO16	31
#define R_MIPS_SCN_DISP		32
#define R_MIPS_REL16		33
#define R_MIPS_ADD_IMMEDIATE	34
#define R_MIPS_PJUMP		35
#define R_MIPS_RELGOT		36
#define R_MIPS_JALR		37
#define R_MIPS_TLS_DTPMOD32	38	/* 模块号 32 位 */
#define R_MIPS_TLS_DTPREL32	39	/* 模块相对偏移 32 位 */
#define R_MIPS_TLS_DTPMOD64	40	/* 模块号 64 位 */
#define R_MIPS_TLS_DTPREL64	41	/* 模块相对偏移 64 位 */
#define R_MIPS_TLS_GD		42	/* GD 的 16 位 GOT 偏移 */
#define R_MIPS_TLS_LDM		43	/* LDM 的 16 位 GOT 偏移 */
#define R_MIPS_TLS_DTPREL_HI16	44	/* 模块相对偏移，高 16 位 */
#define R_MIPS_TLS_DTPREL_LO16	45	/* 模块相对偏移，低 16 位 */
#define R_MIPS_TLS_GOTTPREL	46	/* IE 的 16 位 GOT 偏移 */
#define R_MIPS_TLS_TPREL32	47	/* TP 相对偏移，32 位 */
#define R_MIPS_TLS_TPREL64	48	/* TP 相对偏移，64 位 */
#define R_MIPS_TLS_TPREL_HI16	49	/* TP 相对偏移，高 16 位 */
#define R_MIPS_TLS_TPREL_LO16	50	/* TP 相对偏移，低 16 位 */
#define R_MIPS_GLOB_DAT		51
#define R_MIPS_COPY		126
#define R_MIPS_JUMP_SLOT        127
/* 保持此条目为最后一项。  */
#define R_MIPS_NUM		128

/* Elf32_Phdr 的 p_type 字段的合法值。  */

#define PT_MIPS_REGINFO	0x70000000	/* 寄存器使用信息 */
#define PT_MIPS_RTPROC  0x70000001	/* 运行时过程表。 */
#define PT_MIPS_OPTIONS 0x70000002

/* 特殊程序头类型。  */

#define PF_MIPS_LOCAL	0x10000000

/* Elf32_Dyn 的 d_tag 字段的合法值。  */

#define DT_MIPS_RLD_VERSION  0x70000001	/* 运行时链接器接口版本 */
#define DT_MIPS_TIME_STAMP   0x70000002	/* 时间戳 */
#define DT_MIPS_ICHECKSUM    0x70000003	/* 校验和 */
#define DT_MIPS_IVERSION     0x70000004	/* 版本字符串（字符串表索引） */
#define DT_MIPS_FLAGS	     0x70000005	/* 标志 */
#define DT_MIPS_BASE_ADDRESS 0x70000006	/* 基地址 */
#define DT_MIPS_MSYM	     0x70000007
#define DT_MIPS_CONFLICT     0x70000008	/* CONFLICT 段的地址 */
#define DT_MIPS_LIBLIST	     0x70000009	/* LIBLIST 段的地址 */
#define DT_MIPS_LOCAL_GOTNO  0x7000000a	/* 本地 GOT 条目计数 */
#define DT_MIPS_CONFLICTNO   0x7000000b	/* CONFLICT 条目计数 */
#define DT_MIPS_LIBLISTNO    0x70000010	/* LIBLIST 条目计数 */
#define DT_MIPS_SYMTABNO     0x70000011	/* DYNSYM 条目计数 */
#define DT_MIPS_UNREFEXTNO   0x70000012	/* 第一个外部 DYNSYM */
#define DT_MIPS_GOTSYM	     0x70000013	/* DYNSYM 中第一个 GOT 条目 */
#define DT_MIPS_HIPAGENO     0x70000014	/* GOT 页表条目计数 */
#define DT_MIPS_RLD_MAP	     0x70000016	/* 运行时加载器映射的地址。  */
#define DT_MIPS_DELTA_CLASS  0x70000017	/* Delta C++ 类定义。  */
#define DT_MIPS_DELTA_CLASS_NO    0x70000018 /* DT_MIPS_DELTA_CLASS 中的 条目计数。
  */
#define DT_MIPS_DELTA_INSTANCE    0x70000019 /* Delta C++ 类实例。  */
#define DT_MIPS_DELTA_INSTANCE_NO 0x7000001a /* DT_MIPS_DELTA_INSTANCE 中的 条目计数。
  */
#define DT_MIPS_DELTA_RELOC  0x7000001b /* Delta 重定位。  */
#define DT_MIPS_DELTA_RELOC_NO 0x7000001c /* DT_MIPS_DELTA_RELOC 中的 条目计数。
  */
#define DT_MIPS_DELTA_SYM    0x7000001d /* Delta 重定位所引用的 Delta 符号。
  */
#define DT_MIPS_DELTA_SYM_NO 0x7000001e /* DT_MIPS_DELTA_SYM 中的 条目计数。
  */
#define DT_MIPS_DELTA_CLASSSYM 0x70000020 /* 持有类声明的 Delta 符号。
  */
#define DT_MIPS_DELTA_CLASSSYM_NO 0x70000021 /* DT_MIPS_DELTA_CLASSSYM 中的 条目计数。
  */
#define DT_MIPS_CXX_FLAGS    0x70000022 /* 指示 C++ 风格的标志。  */
#define DT_MIPS_PIXIE_INIT   0x70000023
#define DT_MIPS_SYMBOL_LIB   0x70000024
#define DT_MIPS_LOCALPAGE_GOTIDX 0x70000025
#define DT_MIPS_LOCAL_GOTIDX 0x70000026
#define DT_MIPS_HIDDEN_GOTIDX 0x70000027
#define DT_MIPS_PROTECTED_GOTIDX 0x70000028
#define DT_MIPS_OPTIONS	     0x70000029 /* .options 的地址。  */
#define DT_MIPS_INTERFACE    0x7000002a /* .interface 的地址。  */
#define DT_MIPS_DYNSTR_ALIGN 0x7000002b
#define DT_MIPS_INTERFACE_SIZE 0x7000002c /* .interface 段的大小。 */
#define DT_MIPS_RLD_TEXT_RESOLVE_ADDR 0x7000002d /* 存储在 GOT 中的 rld_text_rsolve
						    函数的地址。  */
#define DT_MIPS_PERF_SUFFIX  0x7000002e /* rld 在 dlopen() 调用时添加的 DSO
					   默认后缀。  */
#define DT_MIPS_COMPACT_SIZE 0x7000002f /* (O32) 紧凑重定位段的大小。 */
#define DT_MIPS_GP_VALUE     0x70000030 /* 辅助 GOT 的 GP 值。  */
#define DT_MIPS_AUX_DYNAMIC  0x70000031 /* 辅助 .dynamic 的地址。  */
/* 使用新非 PIC ABI 的可执行文件中 .got.plt 的地址。  */
#define DT_MIPS_PLTGOT	     0x70000032
/* 使用新非 PIC ABI 的可执行文件中 PLT 的基址（若该 PLT
   可写）。对于不可写的
   PLT，此项省略或为零值。  */
#define DT_MIPS_RWPLT        0x70000034
#define DT_MIPS_NUM	     0x35

/* DT_MIPS_FLAGS Elf32_Dyn 条目的合法值。  */

#define RHF_NONE		   0		/* 无标志 */
#define RHF_QUICKSTART		   (1 << 0)	/* 使用 quickstart */
#define RHF_NOTPOT		   (1 << 1)	/* 哈希大小不是 2 的幂 */
#define RHF_NO_LIBRARY_REPLACEMENT (1 << 2)	/* 忽略 LD_LIBRARY_PATH */
#define RHF_NO_MOVE		   (1 << 3)
#define RHF_SGI_ONLY		   (1 << 4)
#define RHF_GUARANTEE_INIT	   (1 << 5)
#define RHF_DELTA_C_PLUS_PLUS	   (1 << 6)
#define RHF_GUARANTEE_START_INIT   (1 << 7)
#define RHF_PIXIE		   (1 << 8)
#define RHF_DEFAULT_DELAY_LOAD	   (1 << 9)
#define RHF_REQUICKSTART	   (1 << 10)
#define RHF_REQUICKSTARTED	   (1 << 11)
#define RHF_CORD		   (1 << 12)
#define RHF_NO_UNRES_UNDEF	   (1 << 13)
#define RHF_RLD_ORDER_SAFE	   (1 << 14)

/* 在 SHT_MIPS_LIBLIST 类型的段中出现的条目。  */

typedef struct
{
  Elf32_Word l_name;		/* 名称（字符串表索引） */
  Elf32_Word l_time_stamp;	/* 时间戳 */
  Elf32_Word l_checksum;	/* 校验和 */
  Elf32_Word l_version;		/* 接口版本 */
  Elf32_Word l_flags;		/* 标志 */
} Elf32_Lib;

typedef struct
{
  Elf64_Word l_name;		/* 名称（字符串表索引） */
  Elf64_Word l_time_stamp;	/* 时间戳 */
  Elf64_Word l_checksum;	/* 校验和 */
  Elf64_Word l_version;		/* 接口版本 */
  Elf64_Word l_flags;		/* 标志 */
} Elf64_Lib;


/* l_flags 的合法值  */

#define LL_NONE		  0
#define LL_EXACT_MATCH	  (1 << 0)	/* 要求精确匹配 */
#define LL_IGNORE_INT_VER (1 << 1)	/* 忽略接口版本 */
#define LL_REQUIRE_MINOR  (1 << 2)
#define LL_EXPORTS	  (1 << 3)
#define LL_DELAY_LOAD	  (1 << 4)
#define LL_DELTA	  (1 << 5)

/* 在 SHT_MIPS_CONFLICT 类型的段中出现的条目。  */

typedef Elf32_Addr Elf32_Conflict;


/* HPPA 特有定义。  */

/* Elf32_Ehdr 的 e_flags 字段的合法值。  */

#define EF_PARISC_TRAPNIL	0x00010000 /* 捕获空指针解引用。  */
#define EF_PARISC_EXT		0x00020000 /* 程序使用架构扩展。 */
#define EF_PARISC_LSB		0x00040000 /* 程序期望小端。 */
#define EF_PARISC_WIDE		0x00080000 /* 程序期望宽模式。  */
#define EF_PARISC_NO_KABP	0x00100000 /*
					      无内核辅助分支预测。  */
#define EF_PARISC_LAZYSWAP	0x00400000 /* 允许惰性交换。  */
#define EF_PARISC_ARCH		0x0000ffff /* 架构版本。  */

/* `e_flags & EF_PARISC_ARCH' 的定义值有：  */

#define EFA_PARISC_1_0		    0x020b /* PA-RISC 1.0 大端。  */
#define EFA_PARISC_1_1		    0x0210 /* PA-RISC 1.1 大端。  */
#define EFA_PARISC_2_0		    0x0214 /* PA-RISC 2.0 大端。  */

/* 附加段索引。  */

#define SHN_PARISC_ANSI_COMMON	0xff00	   /* ANSI C
					      中暂定声明的符号所在段。  */
#define SHN_PARISC_HUGE_COMMON	0xff01	   /* 大模式下的公共块。  */

/* Elf32_Shdr 的 sh_type 字段的合法值。  */

#define SHT_PARISC_EXT		0x70000000 /* 包含产品特定的扩展。 */
#define SHT_PARISC_UNWIND	0x70000001 /* 展开信息。  */
#define SHT_PARISC_DOC		0x70000002 /* 优化代码的调试信息。 */

/* Elf32_Shdr 的 sh_flags 字段的合法值。  */

#define SHF_PARISC_SHORT	0x20000000 /* 使用短寻址的段。 */
#define SHF_PARISC_HUGE		0x40000000 /* 远离 gp 的段。  */
#define SHF_PARISC_SBP		0x80000000 /* 静态分支预测代码。 */

/* st_info 的 ST_TYPE 子字段（符号类型）的合法值。  */

#define STT_PARISC_MILLICODE	13	/* Millicode 函数入口点。  */

#define STT_HP_OPAQUE		(STT_LOOS + 0x1)
#define STT_HP_STUB		(STT_LOOS + 0x2)

/* HPPA 重定位。  */

#define R_PARISC_NONE		0	/* 无重定位。  */
#define R_PARISC_DIR32		1	/* 直接 32 位引用。  */
#define R_PARISC_DIR21L		2	/* 有效地址的左 21 位。  */
#define R_PARISC_DIR17R		3	/* 有效地址的右 17 位。  */
#define R_PARISC_DIR17F		4	/* 有效地址的 17 位。  */
#define R_PARISC_DIR14R		6	/* 有效地址的右 14 位。  */
#define R_PARISC_PCREL32	9	/* 32 位相对地址。  */
#define R_PARISC_PCREL21L	10	/* 相对地址的左 21 位。  */
#define R_PARISC_PCREL17R	11	/* 相对地址的右 17 位。  */
#define R_PARISC_PCREL17F	12	/* 相对地址的 17 位。  */
#define R_PARISC_PCREL14R	14	/* 相对地址的右 14 位。  */
#define R_PARISC_DPREL21L	18	/* 相对地址的左 21 位。  */
#define R_PARISC_DPREL14R	22	/* 相对地址的右 14 位。  */
#define R_PARISC_GPREL21L	26	/* GP 相对，左 21 位。  */
#define R_PARISC_GPREL14R	30	/* GP 相对，右 14 位。  */
#define R_PARISC_LTOFF21L	34	/* LT 相对，左 21 位。  */
#define R_PARISC_LTOFF14R	38	/* LT 相对，右 14 位。  */
#define R_PARISC_SECREL32	41	/* 32 位段相对地址。  */
#define R_PARISC_SEGBASE	48	/* 无重定位，设置段基址。  */
#define R_PARISC_SEGREL32	49	/* 32 位段相对地址。  */
#define R_PARISC_PLTOFF21L	50	/* PLT 相对地址，左 21 位。  */
#define R_PARISC_PLTOFF14R	54	/* PLT 相对地址，右 14 位。  */
#define R_PARISC_LTOFF_FPTR32	57	/* 32 位 LT 相对函数指针。 */
#define R_PARISC_LTOFF_FPTR21L	58	/* LT 相对函数指针，左 21 位。 */
#define R_PARISC_LTOFF_FPTR14R	62	/* LT 相对函数指针，右 14 位。 */
#define R_PARISC_FPTR64		64	/* 64 位函数地址。  */
#define R_PARISC_PLABEL32	65	/* 32 位函数地址。  */
#define R_PARISC_PLABEL21L	66	/* fdesc 地址的左 21 位。  */
#define R_PARISC_PLABEL14R	70	/* fdesc 地址的右 14 位。  */
#define R_PARISC_PCREL64	72	/* 64 位 PC 相对地址。  */
#define R_PARISC_PCREL22F	74	/* 22 位 PC 相对地址。  */
#define R_PARISC_PCREL14WR	75	/* PC 相对地址，右 14 位。  */
#define R_PARISC_PCREL14DR	76	/* PC 相对地址，右 14 位。  */
#define R_PARISC_PCREL16F	77	/* 16 位 PC 相对地址。  */
#define R_PARISC_PCREL16WF	78	/* 16 位 PC 相对地址。  */
#define R_PARISC_PCREL16DF	79	/* 16 位 PC 相对地址。  */
#define R_PARISC_DIR64		80	/* 有效地址的 64 位。  */
#define R_PARISC_DIR14WR	83	/* 有效地址的 14 位。  */
#define R_PARISC_DIR14DR	84	/* 有效地址的 14 位。  */
#define R_PARISC_DIR16F		85	/* 有效地址的 16 位。  */
#define R_PARISC_DIR16WF	86	/* 有效地址的 16 位。  */
#define R_PARISC_DIR16DF	87	/* 有效地址的 16 位。  */
#define R_PARISC_GPREL64	88	/* 64 位 GP 相对地址。  */
#define R_PARISC_GPREL14WR	91	/* GP 相对地址，右 14 位。  */
#define R_PARISC_GPREL14DR	92	/* GP 相对地址，右 14 位。  */
#define R_PARISC_GPREL16F	93	/* 16 位 GP 相对地址。  */
#define R_PARISC_GPREL16WF	94	/* 16 位 GP 相对地址。  */
#define R_PARISC_GPREL16DF	95	/* 16 位 GP 相对地址。  */
#define R_PARISC_LTOFF64	96	/* 64 位 LT 相对地址。  */
#define R_PARISC_LTOFF14WR	99	/* LT 相对地址，右 14 位。  */
#define R_PARISC_LTOFF14DR	100	/* LT 相对地址，右 14 位。  */
#define R_PARISC_LTOFF16F	101	/* 16 位 LT 相对地址。  */
#define R_PARISC_LTOFF16WF	102	/* 16 位 LT 相对地址。  */
#define R_PARISC_LTOFF16DF	103	/* 16 位 LT 相对地址。  */
#define R_PARISC_SECREL64	104	/* 64 位段相对地址。  */
#define R_PARISC_SEGREL64	112	/* 64 位段相对地址。  */
#define R_PARISC_PLTOFF14WR	115	/* PLT 相对地址，右 14 位。  */
#define R_PARISC_PLTOFF14DR	116	/* PLT 相对地址，右 14 位。  */
#define R_PARISC_PLTOFF16F	117	/* 16 位 LT 相对地址。  */
#define R_PARISC_PLTOFF16WF	118	/* 16 位 PLT 相对地址。  */
#define R_PARISC_PLTOFF16DF	119	/* 16 位 PLT 相对地址。  */
#define R_PARISC_LTOFF_FPTR64	120	/* 64 位 LT 相对函数指针。  */
#define R_PARISC_LTOFF_FPTR14WR	123	/* LT 相对函数指针，右 14 位。 */
#define R_PARISC_LTOFF_FPTR14DR	124	/* LT 相对函数指针，右 14 位。 */
#define R_PARISC_LTOFF_FPTR16F	125	/* 16 位 LT 相对函数指针。  */
#define R_PARISC_LTOFF_FPTR16WF	126	/* 16 位 LT 相对函数指针。  */
#define R_PARISC_LTOFF_FPTR16DF	127	/* 16 位 LT 相对函数指针。  */
#define R_PARISC_LORESERVE	128
#define R_PARISC_COPY		128	/* 复制重定位。  */
#define R_PARISC_IPLT		129	/* 动态重定位，导入的 PLT */
#define R_PARISC_EPLT		130	/* 动态重定位，导出的 PLT */
#define R_PARISC_TPREL32	153	/* 32 位 TP 相对地址。  */
#define R_PARISC_TPREL21L	154	/* TP 相对地址，左 21 位。  */
#define R_PARISC_TPREL14R	158	/* TP 相对地址，右 14 位。  */
#define R_PARISC_LTOFF_TP21L	162	/* LT-TP 相对地址，左 21 位。 */
#define R_PARISC_LTOFF_TP14R	166	/* LT-TP 相对地址，右 14 位。*/
#define R_PARISC_LTOFF_TP14F	167	/* 14 位 LT-TP 相对地址。  */
#define R_PARISC_TPREL64	216	/* 64 位 TP 相对地址。  */
#define R_PARISC_TPREL14WR	219	/* TP 相对地址，右 14 位。  */
#define R_PARISC_TPREL14DR	220	/* TP 相对地址，右 14 位。  */
#define R_PARISC_TPREL16F	221	/* 16 位 TP 相对地址。  */
#define R_PARISC_TPREL16WF	222	/* 16 位 TP 相对地址。  */
#define R_PARISC_TPREL16DF	223	/* 16 位 TP 相对地址。  */
#define R_PARISC_LTOFF_TP64	224	/* 64 位 LT-TP 相对地址。  */
#define R_PARISC_LTOFF_TP14WR	227	/* LT-TP 相对地址，右 14 位。*/
#define R_PARISC_LTOFF_TP14DR	228	/* LT-TP 相对地址，右 14 位。*/
#define R_PARISC_LTOFF_TP16F	229	/* 16 位 LT-TP 相对地址。  */
#define R_PARISC_LTOFF_TP16WF	230	/* 16 位 LT-TP 相对地址。  */
#define R_PARISC_LTOFF_TP16DF	231	/* 16 位 LT-TP 相对地址。  */
#define R_PARISC_GNU_VTENTRY	232
#define R_PARISC_GNU_VTINHERIT	233
#define R_PARISC_TLS_GD21L	234	/* GD 21 位左半。  */
#define R_PARISC_TLS_GD14R	235	/* GD 14 位右半。  */
#define R_PARISC_TLS_GDCALL	236	/* 对 __t_g_a 的 GD 调用。  */
#define R_PARISC_TLS_LDM21L	237	/* LD 模块 21 位左半。  */
#define R_PARISC_TLS_LDM14R	238	/* LD 模块 14 位右半。  */
#define R_PARISC_TLS_LDMCALL	239	/* 对 __t_g_a 的 LD 模块调用。  */
#define R_PARISC_TLS_LDO21L	240	/* LD 偏移 21 位左半。  */
#define R_PARISC_TLS_LDO14R	241	/* LD 偏移 14 位右半。  */
#define R_PARISC_TLS_DTPMOD32	242	/* DTP 模块 32 位。  */
#define R_PARISC_TLS_DTPMOD64	243	/* DTP 模块 64 位。  */
#define R_PARISC_TLS_DTPOFF32	244	/* DTP 偏移 32 位。  */
#define R_PARISC_TLS_DTPOFF64	245	/* DTP 偏移 32 位。  */
#define R_PARISC_TLS_LE21L	R_PARISC_TPREL21L
#define R_PARISC_TLS_LE14R	R_PARISC_TPREL14R
#define R_PARISC_TLS_IE21L	R_PARISC_LTOFF_TP21L
#define R_PARISC_TLS_IE14R	R_PARISC_LTOFF_TP14R
#define R_PARISC_TLS_TPREL32	R_PARISC_TPREL32
#define R_PARISC_TLS_TPREL64	R_PARISC_TPREL64
#define R_PARISC_HIRESERVE	255

/* Elf32_Phdr/Elf64_Phdr 的 p_type 字段的合法值。  */

#define PT_HP_TLS		(PT_LOOS + 0x0)
#define PT_HP_CORE_NONE		(PT_LOOS + 0x1)
#define PT_HP_CORE_VERSION	(PT_LOOS + 0x2)
#define PT_HP_CORE_KERNEL	(PT_LOOS + 0x3)
#define PT_HP_CORE_COMM		(PT_LOOS + 0x4)
#define PT_HP_CORE_PROC		(PT_LOOS + 0x5)
#define PT_HP_CORE_LOADABLE	(PT_LOOS + 0x6)
#define PT_HP_CORE_STACK	(PT_LOOS + 0x7)
#define PT_HP_CORE_SHM		(PT_LOOS + 0x8)
#define PT_HP_CORE_MMF		(PT_LOOS + 0x9)
#define PT_HP_PARALLEL		(PT_LOOS + 0x10)
#define PT_HP_FASTBIND		(PT_LOOS + 0x11)
#define PT_HP_OPT_ANNOT		(PT_LOOS + 0x12)
#define PT_HP_HSL_ANNOT		(PT_LOOS + 0x13)
#define PT_HP_STACK		(PT_LOOS + 0x14)

#define PT_PARISC_ARCHEXT	0x70000000
#define PT_PARISC_UNWIND	0x70000001

/* Elf32_Phdr/Elf64_Phdr 的 p_flags 字段的合法值。  */

#define PF_PARISC_SBP		0x08000000

#define PF_HP_PAGE_SIZE		0x00100000
#define PF_HP_FAR_SHARED	0x00200000
#define PF_HP_NEAR_SHARED	0x00400000
#define PF_HP_CODE		0x01000000
#define PF_HP_MODIFY		0x02000000
#define PF_HP_LAZYSWAP		0x04000000
#define PF_HP_SBP		0x08000000


/* Alpha 特有定义。  */

/* Elf64_Ehdr 的 e_flags 字段的合法值。  */

#define EF_ALPHA_32BIT		1	/* 所有地址必须小于 2GB。  */
#define EF_ALPHA_CANRELAX	2	/* 存在用于松弛的重定位。  */

/* Elf64_Shdr 的 sh_type 字段的合法值。  */

/* 这两者主要涉及 ECOFF 调试信息。  */
#define SHT_ALPHA_DEBUG		0x70000001
#define SHT_ALPHA_REGINFO	0x70000002

/* Elf64_Shdr 的 sh_flags 字段的合法值。  */

#define SHF_ALPHA_GPREL		0x10000000

/* Elf64_Sym 的 st_other 字段的合法值。  */
#define STO_ALPHA_NOPV		0x80	/* 不需要 PV。  */
#define STO_ALPHA_STD_GPLOAD	0x88	/* PV 仅用于初始 ldgp。  */

/* Alpha 重定位。  */

#define R_ALPHA_NONE		0	/* 无重定位 */
#define R_ALPHA_REFLONG		1	/* 直接 32 位 */
#define R_ALPHA_REFQUAD		2	/* 直接 64 位 */
#define R_ALPHA_GPREL32		3	/* GP 相对 32 位 */
#define R_ALPHA_LITERAL		4	/* GP 相对 16 位，带优化 */
#define R_ALPHA_LITUSE		5	/* LITERAL 的优化提示 */
#define R_ALPHA_GPDISP		6	/* 将位移加到 GP */
#define R_ALPHA_BRADDR		7	/* PC+4 相对 23 位，已移位 */
#define R_ALPHA_HINT		8	/* PC+4 相对 16 位，已移位 */
#define R_ALPHA_SREL16		9	/* PC 相对 16 位 */
#define R_ALPHA_SREL32		10	/* PC 相对 32 位 */
#define R_ALPHA_SREL64		11	/* PC 相对 64 位 */
#define R_ALPHA_GPRELHIGH	17	/* GP 相对 32 位，高 16 位 */
#define R_ALPHA_GPRELLOW	18	/* GP 相对 32 位，低 16 位 */
#define R_ALPHA_GPREL16		19	/* GP 相对 16 位 */
#define R_ALPHA_COPY		24	/* 运行时复制符号 */
#define R_ALPHA_GLOB_DAT	25	/* 创建 GOT 条目 */
#define R_ALPHA_JMP_SLOT	26	/* 创建 PLT 条目 */
#define R_ALPHA_RELATIVE	27	/* 按程序基址调整 */
#define R_ALPHA_TLS_GD_HI	28
#define R_ALPHA_TLSGD		29
#define R_ALPHA_TLS_LDM		30
#define R_ALPHA_DTPMOD64	31
#define R_ALPHA_GOTDTPREL	32
#define R_ALPHA_DTPREL64	33
#define R_ALPHA_DTPRELHI	34
#define R_ALPHA_DTPRELLO	35
#define R_ALPHA_DTPREL16	36
#define R_ALPHA_GOTTPREL	37
#define R_ALPHA_TPREL64		38
#define R_ALPHA_TPRELHI		39
#define R_ALPHA_TPRELLO		40
#define R_ALPHA_TPREL16		41
/* 保持此条目为最后一项。  */
#define R_ALPHA_NUM		46

/* LITUSE 重定位加数的魔数值。  */
#define LITUSE_ALPHA_ADDR	0
#define LITUSE_ALPHA_BASE	1
#define LITUSE_ALPHA_BYTOFF	2
#define LITUSE_ALPHA_JSR	3
#define LITUSE_ALPHA_TLS_GD	4
#define LITUSE_ALPHA_TLS_LDM	5

/* Elf64_Dyn 的 d_tag 的合法值。  */
#define DT_ALPHA_PLTRO		(DT_LOPROC + 0)
#define DT_ALPHA_NUM		1

/* PowerPC 特有声明 */

/* Elf32/64_Ehdr.e_flags 的值。  */
#define EF_PPC_EMB		0x80000000	/* PowerPC 嵌入式标志 */

/* 以下为 Cygnus 本地位 */
#define EF_PPC_RELOCATABLE	0x00010000	/* PowerPC -mrelocatable 标志*/
#define EF_PPC_RELOCATABLE_LIB	0x00008000	/* PowerPC -mrelocatable-lib
						   标志 */

/* ABI 定义的 PowerPC 重定位 */
#define R_PPC_NONE		0
#define R_PPC_ADDR32		1	/* 32 位绝对地址 */
#define R_PPC_ADDR24		2	/* 26 位地址，忽略 2 位。  */
#define R_PPC_ADDR16		3	/* 16 位绝对地址 */
#define R_PPC_ADDR16_LO		4	/* 绝对地址的低 16 位 */
#define R_PPC_ADDR16_HI		5	/* 绝对地址的高 16 位 */
#define R_PPC_ADDR16_HA		6	/* 调整后的高 16 位 */
#define R_PPC_ADDR14		7	/* 16 位地址，忽略 2 位 */
#define R_PPC_ADDR14_BRTAKEN	8
#define R_PPC_ADDR14_BRNTAKEN	9
#define R_PPC_REL24		10	/* PC 相对 26 位 */
#define R_PPC_REL14		11	/* PC 相对 16 位 */
#define R_PPC_REL14_BRTAKEN	12
#define R_PPC_REL14_BRNTAKEN	13
#define R_PPC_GOT16		14
#define R_PPC_GOT16_LO		15
#define R_PPC_GOT16_HI		16
#define R_PPC_GOT16_HA		17
#define R_PPC_PLTREL24		18
#define R_PPC_COPY		19
#define R_PPC_GLOB_DAT		20
#define R_PPC_JMP_SLOT		21
#define R_PPC_RELATIVE		22
#define R_PPC_LOCAL24PC		23
#define R_PPC_UADDR32		24
#define R_PPC_UADDR16		25
#define R_PPC_REL32		26
#define R_PPC_PLT32		27
#define R_PPC_PLTREL32		28
#define R_PPC_PLT16_LO		29
#define R_PPC_PLT16_HI		30
#define R_PPC_PLT16_HA		31
#define R_PPC_SDAREL16		32
#define R_PPC_SECTOFF		33
#define R_PPC_SECTOFF_LO	34
#define R_PPC_SECTOFF_HI	35
#define R_PPC_SECTOFF_HA	36

/* 为 TLS 访问 ABI 定义的 PowerPC 重定位。  */
#define R_PPC_TLS		67 /* none	(sym+add)@tls */
#define R_PPC_DTPMOD32		68 /* word32	(sym+add)@dtpmod */
#define R_PPC_TPREL16		69 /* half16*	(sym+add)@tprel */
#define R_PPC_TPREL16_LO	70 /* half16	(sym+add)@tprel@l */
#define R_PPC_TPREL16_HI	71 /* half16	(sym+add)@tprel@h */
#define R_PPC_TPREL16_HA	72 /* half16	(sym+add)@tprel@ha */
#define R_PPC_TPREL32		73 /* word32	(sym+add)@tprel */
#define R_PPC_DTPREL16		74 /* half16*	(sym+add)@dtprel */
#define R_PPC_DTPREL16_LO	75 /* half16	(sym+add)@dtprel@l */
#define R_PPC_DTPREL16_HI	76 /* half16	(sym+add)@dtprel@h */
#define R_PPC_DTPREL16_HA	77 /* half16	(sym+add)@dtprel@ha */
#define R_PPC_DTPREL32		78 /* word32	(sym+add)@dtprel */
#define R_PPC_GOT_TLSGD16	79 /* half16*	(sym+add)@got@tlsgd */
#define R_PPC_GOT_TLSGD16_LO	80 /* half16	(sym+add)@got@tlsgd@l */
#define R_PPC_GOT_TLSGD16_HI	81 /* half16	(sym+add)@got@tlsgd@h */
#define R_PPC_GOT_TLSGD16_HA	82 /* half16	(sym+add)@got@tlsgd@ha */
#define R_PPC_GOT_TLSLD16	83 /* half16*	(sym+add)@got@tlsld */
#define R_PPC_GOT_TLSLD16_LO	84 /* half16	(sym+add)@got@tlsld@l */
#define R_PPC_GOT_TLSLD16_HI	85 /* half16	(sym+add)@got@tlsld@h */
#define R_PPC_GOT_TLSLD16_HA	86 /* half16	(sym+add)@got@tlsld@ha */
#define R_PPC_GOT_TPREL16	87 /* half16*	(sym+add)@got@tprel */
#define R_PPC_GOT_TPREL16_LO	88 /* half16	(sym+add)@got@tprel@l */
#define R_PPC_GOT_TPREL16_HI	89 /* half16	(sym+add)@got@tprel@h */
#define R_PPC_GOT_TPREL16_HA	90 /* half16	(sym+add)@got@tprel@ha */
#define R_PPC_GOT_DTPREL16	91 /* half16*	(sym+add)@got@dtprel */
#define R_PPC_GOT_DTPREL16_LO	92 /* half16*	(sym+add)@got@dtprel@l */
#define R_PPC_GOT_DTPREL16_HI	93 /* half16*	(sym+add)@got@dtprel@h */
#define R_PPC_GOT_DTPREL16_HA	94 /* half16*	(sym+add)@got@dtprel@ha */

/* 其余重定位来自嵌入式 ELF ABI，不在 SVR4 ELF ABI
   中。  */
#define R_PPC_EMB_NADDR32	101
#define R_PPC_EMB_NADDR16	102
#define R_PPC_EMB_NADDR16_LO	103
#define R_PPC_EMB_NADDR16_HI	104
#define R_PPC_EMB_NADDR16_HA	105
#define R_PPC_EMB_SDAI16	106
#define R_PPC_EMB_SDA2I16	107
#define R_PPC_EMB_SDA2REL	108
#define R_PPC_EMB_SDA21		109	/* SDA 中的 16 位偏移 */
#define R_PPC_EMB_MRKREF	110
#define R_PPC_EMB_RELSEC16	111
#define R_PPC_EMB_RELST_LO	112
#define R_PPC_EMB_RELST_HI	113
#define R_PPC_EMB_RELST_HA	114
#define R_PPC_EMB_BIT_FLD	115
#define R_PPC_EMB_RELSDA	116	/* SDA 中的 16 位相对偏移 */

/* Diab 工具重定位。  */
#define R_PPC_DIAB_SDA21_LO	180	/* 类似 EMB_SDA21，但为低 16 位 */
#define R_PPC_DIAB_SDA21_HI	181	/* 类似 EMB_SDA21，但为高 16 位 */
#define R_PPC_DIAB_SDA21_HA	182	/* 类似 EMB_SDA21，调整后的高 16 位 */
#define R_PPC_DIAB_RELSDA_LO	183	/* 类似 EMB_RELSDA，但为低 16 位 */
#define R_PPC_DIAB_RELSDA_HI	184	/* 类似 EMB_RELSDA，但为高 16 位 */
#define R_PPC_DIAB_RELSDA_HA	185	/* 类似 EMB_RELSDA，调整后的高 16 位 */

/* 支持本地 ifunc 的 GNU 扩展。  */
#define R_PPC_IRELATIVE		248

/* PIC 代码序列中使用的 GNU 重定位。  */
#define R_PPC_REL16		249	/* half16   (sym+add-.) */
#define R_PPC_REL16_LO		250	/* half16   (sym+add-.)@l */
#define R_PPC_REL16_HI		251	/* half16   (sym+add-.)@h */
#define R_PPC_REL16_HA		252	/* half16   (sym+add-.)@ha */

/* 这是一个伪重定位，用于处理目标文件中可能仍存在的旧式 TOC16
   引用。  */
#define R_PPC_TOC16		255

/* Dyn 的 d_tag 字段的 PowerPC 特有值。  */
#define DT_PPC_GOT		(DT_LOPROC + 0)
#define DT_PPC_NUM		1

/* ABI 定义的 PowerPC64 重定位 */
#define R_PPC64_NONE		R_PPC_NONE
#define R_PPC64_ADDR32		R_PPC_ADDR32 /* 32 位绝对地址 */
#define R_PPC64_ADDR24		R_PPC_ADDR24 /* 26 位地址，按字对齐 */
#define R_PPC64_ADDR16		R_PPC_ADDR16 /* 16 位绝对地址 */
#define R_PPC64_ADDR16_LO	R_PPC_ADDR16_LO	/* 地址的低 16 位 */
#define R_PPC64_ADDR16_HI	R_PPC_ADDR16_HI	/* 地址的高 16 位。 */
#define R_PPC64_ADDR16_HA	R_PPC_ADDR16_HA /* 调整后的高 16 位。  */
#define R_PPC64_ADDR14		R_PPC_ADDR14 /* 16 位地址，按字对齐 */
#define R_PPC64_ADDR14_BRTAKEN	R_PPC_ADDR14_BRTAKEN
#define R_PPC64_ADDR14_BRNTAKEN	R_PPC_ADDR14_BRNTAKEN
#define R_PPC64_REL24		R_PPC_REL24 /* PC 相对 26 位，按字对齐 */
#define R_PPC64_REL14		R_PPC_REL14 /* PC 相对 16 位 */
#define R_PPC64_REL14_BRTAKEN	R_PPC_REL14_BRTAKEN
#define R_PPC64_REL14_BRNTAKEN	R_PPC_REL14_BRNTAKEN
#define R_PPC64_GOT16		R_PPC_GOT16
#define R_PPC64_GOT16_LO	R_PPC_GOT16_LO
#define R_PPC64_GOT16_HI	R_PPC_GOT16_HI
#define R_PPC64_GOT16_HA	R_PPC_GOT16_HA

#define R_PPC64_COPY		R_PPC_COPY
#define R_PPC64_GLOB_DAT	R_PPC_GLOB_DAT
#define R_PPC64_JMP_SLOT	R_PPC_JMP_SLOT
#define R_PPC64_RELATIVE	R_PPC_RELATIVE

#define R_PPC64_UADDR32		R_PPC_UADDR32
#define R_PPC64_UADDR16		R_PPC_UADDR16
#define R_PPC64_REL32		R_PPC_REL32
#define R_PPC64_PLT32		R_PPC_PLT32
#define R_PPC64_PLTREL32	R_PPC_PLTREL32
#define R_PPC64_PLT16_LO	R_PPC_PLT16_LO
#define R_PPC64_PLT16_HI	R_PPC_PLT16_HI
#define R_PPC64_PLT16_HA	R_PPC_PLT16_HA

#define R_PPC64_SECTOFF		R_PPC_SECTOFF
#define R_PPC64_SECTOFF_LO	R_PPC_SECTOFF_LO
#define R_PPC64_SECTOFF_HI	R_PPC_SECTOFF_HI
#define R_PPC64_SECTOFF_HA	R_PPC_SECTOFF_HA
#define R_PPC64_ADDR30		37 /* word30 (S + A - P) >> 2 */
#define R_PPC64_ADDR64		38 /* doubleword64 S + A */
#define R_PPC64_ADDR16_HIGHER	39 /* half16 #higher(S + A) */
#define R_PPC64_ADDR16_HIGHERA	40 /* half16 #highera(S + A) */
#define R_PPC64_ADDR16_HIGHEST	41 /* half16 #highest(S + A) */
#define R_PPC64_ADDR16_HIGHESTA	42 /* half16 #highesta(S + A) */
#define R_PPC64_UADDR64		43 /* doubleword64 S + A */
#define R_PPC64_REL64		44 /* doubleword64 S + A - P */
#define R_PPC64_PLT64		45 /* doubleword64 L + A */
#define R_PPC64_PLTREL64	46 /* doubleword64 L + A - P */
#define R_PPC64_TOC16		47 /* half16* S + A - .TOC */
#define R_PPC64_TOC16_LO	48 /* half16 #lo(S + A - .TOC.) */
#define R_PPC64_TOC16_HI	49 /* half16 #hi(S + A - .TOC.) */
#define R_PPC64_TOC16_HA	50 /* half16 #ha(S + A - .TOC.) */
#define R_PPC64_TOC		51 /* doubleword64 .TOC */
#define R_PPC64_PLTGOT16	52 /* half16* M + A */
#define R_PPC64_PLTGOT16_LO	53 /* half16 #lo(M + A) */
#define R_PPC64_PLTGOT16_HI	54 /* half16 #hi(M + A) */
#define R_PPC64_PLTGOT16_HA	55 /* half16 #ha(M + A) */

#define R_PPC64_ADDR16_DS	56 /* half16ds* (S + A) >> 2 */
#define R_PPC64_ADDR16_LO_DS	57 /* half16ds  #lo(S + A) >> 2 */
#define R_PPC64_GOT16_DS	58 /* half16ds* (G + A) >> 2 */
#define R_PPC64_GOT16_LO_DS	59 /* half16ds  #lo(G + A) >> 2 */
#define R_PPC64_PLT16_LO_DS	60 /* half16ds  #lo(L + A) >> 2 */
#define R_PPC64_SECTOFF_DS	61 /* half16ds* (R + A) >> 2 */
#define R_PPC64_SECTOFF_LO_DS	62 /* half16ds  #lo(R + A) >> 2 */
#define R_PPC64_TOC16_DS	63 /* half16ds* (S + A - .TOC.) >> 2 */
#define R_PPC64_TOC16_LO_DS	64 /* half16ds  #lo(S + A - .TOC.) >> 2 */
#define R_PPC64_PLTGOT16_DS	65 /* half16ds* (M + A) >> 2 */
#define R_PPC64_PLTGOT16_LO_DS	66 /* half16ds  #lo(M + A) >> 2 */

/* 为 TLS 访问 ABI 定义的 PowerPC64 重定位。  */
#define R_PPC64_TLS		67 /* none	(sym+add)@tls */
#define R_PPC64_DTPMOD64	68 /* doubleword64 (sym+add)@dtpmod */
#define R_PPC64_TPREL16		69 /* half16*	(sym+add)@tprel */
#define R_PPC64_TPREL16_LO	70 /* half16	(sym+add)@tprel@l */
#define R_PPC64_TPREL16_HI	71 /* half16	(sym+add)@tprel@h */
#define R_PPC64_TPREL16_HA	72 /* half16	(sym+add)@tprel@ha */
#define R_PPC64_TPREL64		73 /* doubleword64 (sym+add)@tprel */
#define R_PPC64_DTPREL16	74 /* half16*	(sym+add)@dtprel */
#define R_PPC64_DTPREL16_LO	75 /* half16	(sym+add)@dtprel@l */
#define R_PPC64_DTPREL16_HI	76 /* half16	(sym+add)@dtprel@h */
#define R_PPC64_DTPREL16_HA	77 /* half16	(sym+add)@dtprel@ha */
#define R_PPC64_DTPREL64	78 /* doubleword64 (sym+add)@dtprel */
#define R_PPC64_GOT_TLSGD16	79 /* half16*	(sym+add)@got@tlsgd */
#define R_PPC64_GOT_TLSGD16_LO	80 /* half16	(sym+add)@got@tlsgd@l */
#define R_PPC64_GOT_TLSGD16_HI	81 /* half16	(sym+add)@got@tlsgd@h */
#define R_PPC64_GOT_TLSGD16_HA	82 /* half16	(sym+add)@got@tlsgd@ha */
#define R_PPC64_GOT_TLSLD16	83 /* half16*	(sym+add)@got@tlsld */
#define R_PPC64_GOT_TLSLD16_LO	84 /* half16	(sym+add)@got@tlsld@l */
#define R_PPC64_GOT_TLSLD16_HI	85 /* half16	(sym+add)@got@tlsld@h */
#define R_PPC64_GOT_TLSLD16_HA	86 /* half16	(sym+add)@got@tlsld@ha */
#define R_PPC64_GOT_TPREL16_DS	87 /* half16ds*	(sym+add)@got@tprel */
#define R_PPC64_GOT_TPREL16_LO_DS 88 /* half16ds (sym+add)@got@tprel@l */
#define R_PPC64_GOT_TPREL16_HI	89 /* half16	(sym+add)@got@tprel@h */
#define R_PPC64_GOT_TPREL16_HA	90 /* half16	(sym+add)@got@tprel@ha */
#define R_PPC64_GOT_DTPREL16_DS	91 /* half16ds*	(sym+add)@got@dtprel */
#define R_PPC64_GOT_DTPREL16_LO_DS 92 /* half16ds (sym+add)@got@dtprel@l */
#define R_PPC64_GOT_DTPREL16_HI	93 /* half16	(sym+add)@got@dtprel@h */
#define R_PPC64_GOT_DTPREL16_HA	94 /* half16	(sym+add)@got@dtprel@ha */
#define R_PPC64_TPREL16_DS	95 /* half16ds*	(sym+add)@tprel */
#define R_PPC64_TPREL16_LO_DS	96 /* half16ds	(sym+add)@tprel@l */
#define R_PPC64_TPREL16_HIGHER	97 /* half16	(sym+add)@tprel@higher */
#define R_PPC64_TPREL16_HIGHERA	98 /* half16	(sym+add)@tprel@highera */
#define R_PPC64_TPREL16_HIGHEST	99 /* half16	(sym+add)@tprel@highest */
#define R_PPC64_TPREL16_HIGHESTA 100 /* half16	(sym+add)@tprel@highesta */
#define R_PPC64_DTPREL16_DS	101 /* half16ds* (sym+add)@dtprel */
#define R_PPC64_DTPREL16_LO_DS	102 /* half16ds	(sym+add)@dtprel@l */
#define R_PPC64_DTPREL16_HIGHER	103 /* half16	(sym+add)@dtprel@higher */
#define R_PPC64_DTPREL16_HIGHERA 104 /* half16	(sym+add)@dtprel@highera */
#define R_PPC64_DTPREL16_HIGHEST 105 /* half16	(sym+add)@dtprel@highest */
#define R_PPC64_DTPREL16_HIGHESTA 106 /* half16	(sym+add)@dtprel@highesta */

/* 支持本地 ifunc 的 GNU 扩展。  */
#define R_PPC64_JMP_IREL	247
#define R_PPC64_IRELATIVE	248
#define R_PPC64_REL16		249	/* half16   (sym+add-.) */
#define R_PPC64_REL16_LO	250	/* half16   (sym+add-.)@l */
#define R_PPC64_REL16_HI	251	/* half16   (sym+add-.)@h */
#define R_PPC64_REL16_HA	252	/* half16   (sym+add-.)@ha */

/* Dyn 的 d_tag 字段的 PowerPC64 特有值。  */
#define DT_PPC64_GLINK  (DT_LOPROC + 0)
#define DT_PPC64_OPD	(DT_LOPROC + 1)
#define DT_PPC64_OPDSZ	(DT_LOPROC + 2)
#define DT_PPC64_NUM    3


/* ARM 特有声明 */

/* ELF 头 e_flags 字段的处理器特有标志。  */
#define EF_ARM_RELEXEC		0x01
#define EF_ARM_HASENTRY		0x02
#define EF_ARM_INTERWORK	0x04
#define EF_ARM_APCS_26		0x08
#define EF_ARM_APCS_FLOAT	0x10
#define EF_ARM_PIC		0x20
#define EF_ARM_ALIGN8		0x40 /* 正在使用 8 位结构对齐 */
#define EF_ARM_NEW_ABI		0x80
#define EF_ARM_OLD_ABI		0x100
#define EF_ARM_SOFT_FLOAT	0x200
#define EF_ARM_VFP_FLOAT	0x400
#define EF_ARM_MAVERICK_FLOAT	0x800

#define EF_ARM_ABI_FLOAT_SOFT	0x200   /* 注意与 EF_ARM_SOFT_FLOAT 冲突 */
#define EF_ARM_ABI_FLOAT_HARD	0x400   /* 注意与 EF_ARM_VFP_FLOAT 冲突 */


/* ARM ELF 规范版本 B-01 中定义的其他常量。  */
/* 注意：这些与上面定义的值冲突。  */
#define EF_ARM_SYMSARESORTED	0x04
#define EF_ARM_DYNSYMSUSESEGIDX	0x08
#define EF_ARM_MAPSYMSFIRST	0x10
#define EF_ARM_EABIMASK		0XFF000000

/* AAELF 中定义的常量。  */
#define EF_ARM_BE8	    0x00800000
#define EF_ARM_LE8	    0x00400000

#define EF_ARM_EABI_VERSION(flags)	((flags) & EF_ARM_EABIMASK)
#define EF_ARM_EABI_UNKNOWN	0x00000000
#define EF_ARM_EABI_VER1	0x01000000
#define EF_ARM_EABI_VER2	0x02000000
#define EF_ARM_EABI_VER3	0x03000000
#define EF_ARM_EABI_VER4	0x04000000
#define EF_ARM_EABI_VER5	0x05000000

/* Thumb 的附加符号类型。  */
#define STT_ARM_TFUNC		STT_LOPROC /* 一个 Thumb 函数。  */
#define STT_ARM_16BIT		STT_HIPROC /* 一个 Thumb 标签。  */

/* sh_flags 的 ARM 特有值 */
#define SHF_ARM_ENTRYSECT	0x10000000 /* 段包含一个入口点 */
#define SHF_ARM_COMDEF		0x80000000 /*
					      段在链接步骤的输入中可能被多次定义。  */

/* ARM 特有的程序头标志 */
#define PF_ARM_SB		0x10000000 /*
					      段包含静态基址所指向的位置。 */
#define PF_ARM_PI		0x20000000 /* 位置无关段。  */
#define PF_ARM_ABS		0x40000000 /* 绝对段。  */

/* Phdr 的 p_type 字段的处理器特有值。  */
#define PT_ARM_EXIDX		(PT_LOPROC + 1)	/* ARM 展开段。  */

/* Shdr 的 sh_type 字段的处理器特有值。  */
#define SHT_ARM_EXIDX		(SHT_LOPROC + 1) /* ARM 展开段。  */
#define SHT_ARM_PREEMPTMAP	(SHT_LOPROC + 2) /* 抢占细节。  */
#define SHT_ARM_ATTRIBUTES	(SHT_LOPROC + 3) /* ARM 属性段。  */


/* AArch64 重定位。  */

#define R_AARCH64_NONE            0	/* 无重定位。  */
#define R_AARCH64_ABS64         257	/* 直接 64 位。 */
#define R_AARCH64_ABS32         258	/* 直接 32 位。  */
#define R_AARCH64_ABS16         259	/* 直接 16 位。  */
#define R_AARCH64_PREL64        260	/* PC 相对 64 位。  */
#define R_AARCH64_PREL32        261	/* PC 相对 32 位。  */
#define R_AARCH64_PREL16        262	/* PC 相对 16 位。  */
#define R_AARCH64_MOVW_UABS_G0  263	/* 直接 MOVZ 立即数，取自位 15:0。  */
#define R_AARCH64_MOVW_UABS_G0_NC 264	/* 对 MOVK 同理；不做检查。  */
#define R_AARCH64_MOVW_UABS_G1  265	/* 直接 MOVZ 立即数，取自位 31:16。  */
#define R_AARCH64_MOVW_UABS_G1_NC 266	/* 对 MOVK 同理；不做检查。  */
#define R_AARCH64_MOVW_UABS_G2  267	/* 直接 MOVZ 立即数，取自位 47:32。  */
#define R_AARCH64_MOVW_UABS_G2_NC 268	/* 对 MOVK 同理；不做检查。  */
#define R_AARCH64_MOVW_UABS_G3  269	/* 直接 MOV{K,Z} 立即数，取自 63:48。  */
#define R_AARCH64_MOVW_SABS_G0  270	/* 直接 MOV{N,Z} 立即数，取自 15:0。  */
#define R_AARCH64_MOVW_SABS_G1  271	/* 直接 MOV{N,Z} 立即数，取自 31:16。  */
#define R_AARCH64_MOVW_SABS_G2  272	/* 直接 MOV{N,Z} 立即数，取自 47:32。  */
#define R_AARCH64_LD_PREL_LO19  273	/* PC 相对 LD 立即数，取自位 20:2。  */
#define R_AARCH64_ADR_PREL_LO21 274	/* PC 相对 ADR 立即数，取自位 20:0。  */
#define R_AARCH64_ADR_PREL_PG_HI21 275	/* 页相对 ADRP 立即数，取自 32:12。  */
#define R_AARCH64_ADR_PREL_PG_HI21_NC 276	/* 同理；不做溢出检查。  */
#define R_AARCH64_ADD_ABS_LO12_NC 277	/* 直接 ADD 立即数，取自位 11:0。  */
#define R_AARCH64_LDST8_ABS_LO12_NC 278	/* 对 LD/ST 同理；不做检查。 */
#define R_AARCH64_TSTBR14       279	/* PC 相对 TBZ/TBNZ 立即数，取自 15:2。  */
#define R_AARCH64_CONDBR19      280	/* PC 相对条件分支立即数，取自 20:2。 */
#define R_AARCH64_JUMP26        282	/* PC 相对 B 立即数，取自位 27:2。  */
#define R_AARCH64_CALL26        283	/* 对 CALL 同理。  */
#define R_AARCH64_LDST16_ABS_LO12_NC 284	/* 直接 ADD 立即数，取自位 11:1。  */
#define R_AARCH64_LDST32_ABS_LO12_NC 285	/* 对位 11:2 同理。  */
#define R_AARCH64_LDST64_ABS_LO12_NC 286	/* 对位 11:3 同理。  */
#define R_AARCH64_MOVW_PREL_G0  287	/* PC 相对 MOV{N,Z} 立即数，取自 15:0。  */
#define R_AARCH64_MOVW_PREL_G0_NC 288	/* 对 MOVK 同理；不做检查。  */
#define R_AARCH64_MOVW_PREL_G1  289	/* PC 相对 MOV{N,Z} 立即数，取自 31:16。 */
#define R_AARCH64_MOVW_PREL_G1_NC 290	/* 对 MOVK 同理；不做检查。  */
#define R_AARCH64_MOVW_PREL_G2  291	/* PC 相对 MOV{N,Z} 立即数，取自 47:32。 */
#define R_AARCH64_MOVW_PREL_G2_NC 292	/* 对 MOVK 同理；不做检查。  */
#define R_AARCH64_MOVW_PREL_G3  293	/* PC 相对 MOV{N,Z} 立即数，取自 63:48。 */
#define R_AARCH64_LDST128_ABS_LO12_NC 299	/* 直接 ADD 立即数，取自位 11:4。  */
#define R_AARCH64_MOVW_GOTOFF_G0 300	/* GOT 相对偏移 MOV{N,Z} 立即数 15:0。 */
#define R_AARCH64_MOVW_GOTOFF_G0_NC 301	/* 对 MOVK 同理；不做检查。  */
#define R_AARCH64_MOVW_GOTOFF_G1 302	/* GOT 相对偏移 MOV{N,Z} 立即数 31:16。  */
#define R_AARCH64_MOVW_GOTOFF_G1_NC 303	/* 对 MOVK 同理；不做检查。  */
#define R_AARCH64_MOVW_GOTOFF_G2 304	/* GOT 相对偏移 MOV{N,Z} 立即数 47:32。  */
#define R_AARCH64_MOVW_GOTOFF_G2_NC 305	/* 对 MOVK 同理；不做检查。  */
#define R_AARCH64_MOVW_GOTOFF_G3 306	/* GOT 相对偏移 MOV{N,Z} 立即数 63:48。  */
#define R_AARCH64_GOTREL64      307	/* GOT 相对 64 位。  */
#define R_AARCH64_GOTREL32      308	/* GOT 相对 32 位。  */
#define R_AARCH64_GOT_LD_PREL19 309	/* PC 相对 GOT 偏移加载立即数 20:2。  */
#define R_AARCH64_LD64_GOTOFF_LO15 310	/* GOT 相对偏移 LD/ST 立即数 14:3。  */
#define R_AARCH64_ADR_GOT_PAGE  311	/* P 页相对 GOT 偏移 ADRP 32:12。  */
#define R_AARCH64_LD64_GOT_LO12_NC 312	/* 直接 GOT 偏移 LD/ST 立即数 11:3。  */
#define R_AARCH64_LD64_GOTPAGE_LO15 313	/* GOT 页相对 GOT 偏移 LD/ST 14:3 */
#define R_AARCH64_TLSGD_ADR_PREL21 512	/* PC 相对 ADR 立即数 20:0。  */
#define R_AARCH64_TLSGD_ADR_PAGE21 513	/* 页相对 ADRP 立即数 32:12。  */
#define R_AARCH64_TLSGD_ADD_LO12_NC 514	/* 直接 ADD 立即数，取自 11:0。  */
#define R_AARCH64_TLSGD_MOVW_G1 515	/* GOT 相对 MOV{N,Z} 31:16。  */
#define R_AARCH64_TLSGD_MOVW_G0_NC 516	/* GOT 相对 MOVK 立即数 15:0。  */
#define R_AARCH64_TLSLD_ADR_PREL21 517	/* 类似 512；局部动态模型。  */
#define R_AARCH64_TLSLD_ADR_PAGE21 518	/* 类似 513；局部动态模型。  */
#define R_AARCH64_TLSLD_ADD_LO12_NC 519	/* 类似 514；局部动态模型。  */
#define R_AARCH64_TLSLD_MOVW_G1 520	/* 类似 515；局部动态模型。  */
#define R_AARCH64_TLSLD_MOVW_G0_NC 521	/* 类似 516；局部动态模型。  */
#define R_AARCH64_TLSLD_LD_PREL19 522	/* TLS PC 相对加载立即数 20:2。  */
#define R_AARCH64_TLSLD_MOVW_DTPREL_G2 523	/* TLS DTP 相对 MOV{N,Z} 47:32。  */
#define R_AARCH64_TLSLD_MOVW_DTPREL_G1 524	/* TLS DTP 相对 MOV{N,Z} 31:16。  */
#define R_AARCH64_TLSLD_MOVW_DTPREL_G1_NC 525	/* 同理；MOVK；不做检查。  */
#define R_AARCH64_TLSLD_MOVW_DTPREL_G0 526	/* TLS DTP 相对 MOV{N,Z} 15:0。  */
#define R_AARCH64_TLSLD_MOVW_DTPREL_G0_NC 527	/* 同理；MOVK；不做检查。  */
#define R_AARCH64_TLSLD_ADD_DTPREL_HI12 528	/* DTP 相对 ADD 立即数，取自 23:12。 */
#define R_AARCH64_TLSLD_ADD_DTPREL_LO12 529	/* DTP 相对 ADD 立即数，取自 11:0。  */
#define R_AARCH64_TLSLD_ADD_DTPREL_LO12_NC 530	/* 同理；不做溢出检查。  */
#define R_AARCH64_TLSLD_LDST8_DTPREL_LO12 531	/* DTP 相对 LD/ST 立即数 11:0。  */
#define R_AARCH64_TLSLD_LDST8_DTPREL_LO12_NC 532	/* 同理；不做检查。  */
#define R_AARCH64_TLSLD_LDST16_DTPREL_LO12 533	/* DTP 相对 LD/ST 立即数 11:1。  */
#define R_AARCH64_TLSLD_LDST16_DTPREL_LO12_NC 534	/* 同理；不做检查。  */
#define R_AARCH64_TLSLD_LDST32_DTPREL_LO12 535	/* DTP 相对 LD/ST 立即数 11:2。  */
#define R_AARCH64_TLSLD_LDST32_DTPREL_LO12_NC 536	/* 同理；不做检查。  */
#define R_AARCH64_TLSLD_LDST64_DTPREL_LO12 537	/* DTP 相对 LD/ST 立即数 11:3。  */
#define R_AARCH64_TLSLD_LDST64_DTPREL_LO12_NC 538	/* 同理；不做检查。  */
#define R_AARCH64_TLSIE_MOVW_GOTTPREL_G1 539	/* GOT 相对 MOV{N,Z} 31:16。  */
#define R_AARCH64_TLSIE_MOVW_GOTTPREL_G0_NC 540	/* GOT 相对 MOVK 15:0。  */
#define R_AARCH64_TLSIE_ADR_GOTTPREL_PAGE21 541	/* 页相对 ADRP 32:12。  */
#define R_AARCH64_TLSIE_LD64_GOTTPREL_LO12_NC 542	/* 直接 LD 偏移 11:3。  */
#define R_AARCH64_TLSIE_LD_GOTTPREL_PREL19 543	/* PC 相对加载立即数 20:2。  */
#define R_AARCH64_TLSLE_MOVW_TPREL_G2 544	/* TLS TP 相对 MOV{N,Z} 47:32。  */
#define R_AARCH64_TLSLE_MOVW_TPREL_G1 545	/* TLS TP 相对 MOV{N,Z} 31:16。  */
#define R_AARCH64_TLSLE_MOVW_TPREL_G1_NC 546	/* 同理；MOVK；不做检查。  */
#define R_AARCH64_TLSLE_MOVW_TPREL_G0 547	/* TLS TP 相对 MOV{N,Z} 15:0。  */
#define R_AARCH64_TLSLE_MOVW_TPREL_G0_NC 548	/* 同理；MOVK；不做检查。  */
#define R_AARCH64_TLSLE_ADD_TPREL_HI12 549	/* TP 相对 ADD 立即数 23:12。  */
#define R_AARCH64_TLSLE_ADD_TPREL_LO12 550	/* TP 相对 ADD 立即数 11:0。  */
#define R_AARCH64_TLSLE_ADD_TPREL_LO12_NC 551	/* 同理；不做溢出检查。  */
#define R_AARCH64_TLSLE_LDST8_TPREL_LO12 552	/* TP 相对 LD/ST 偏移 11:0。  */
#define R_AARCH64_TLSLE_LDST8_TPREL_LO12_NC 553	/* 同理；不做溢出检查。 */
#define R_AARCH64_TLSLE_LDST16_TPREL_LO12 554	/* TP 相对 LD/ST 偏移 11:1。  */
#define R_AARCH64_TLSLE_LDST16_TPREL_LO12_NC 555	/* 同理；不做检查。  */
#define R_AARCH64_TLSLE_LDST32_TPREL_LO12 556	/* TP 相对 LD/ST 偏移 11:2。  */
#define R_AARCH64_TLSLE_LDST32_TPREL_LO12_NC 557	/* 同理；不做检查。  */
#define R_AARCH64_TLSLE_LDST64_TPREL_LO12 558	/* TP 相对 LD/ST 偏移 11:3。  */
#define R_AARCH64_TLSLE_LDST64_TPREL_LO12_NC 559	/* 同理；不做检查。  */
#define R_AARCH64_TLSDESC_LD_PREL19 560	/* PC 相对加载立即数 20:2。  */
#define R_AARCH64_TLSDESC_ADR_PREL21 561	/* PC 相对 ADR 立即数 20:0。  */
#define R_AARCH64_TLSDESC_ADR_PAGE21 562	/* 页相对 ADRP 立即数 32:12。  */
#define R_AARCH64_TLSDESC_LD64_LO12 563	/* 直接 LD 偏移，取自 11:3。  */
#define R_AARCH64_TLSDESC_ADD_LO12 564	/* 直接 ADD 立即数，取自 11:0。  */
#define R_AARCH64_TLSDESC_OFF_G1 565	/* GOT 相对 MOV{N,Z} 立即数 31:16。  */
#define R_AARCH64_TLSDESC_OFF_G0_NC 566	/* GOT 相对 MOVK 立即数 15:0；不检查。  */
#define R_AARCH64_TLSDESC_LDR   567	/* 松弛 LDR。  */
#define R_AARCH64_TLSDESC_ADD   568	/* 松弛 ADD。  */
#define R_AARCH64_TLSDESC_CALL  569	/* 松弛 BLR。  */
#define R_AARCH64_TLSLE_LDST128_TPREL_LO12 570	/* TP 相对 LD/ST 偏移 11:4。  */
#define R_AARCH64_TLSLE_LDST128_TPREL_LO12_NC 571	/* 同理；不做检查。  */
#define R_AARCH64_TLSLD_LDST128_DTPREL_LO12 572	/* DTP 相对 LD/ST 立即数 11:4。 */
#define R_AARCH64_TLSLD_LDST128_DTPREL_LO12_NC 573	/* 同理；不做检查。  */
#define R_AARCH64_COPY         1024	/* 在运行时复制符号。  */
#define R_AARCH64_GLOB_DAT     1025	/* 创建 GOT 条目。  */
#define R_AARCH64_JUMP_SLOT    1026	/* 创建 PLT 条目。  */
#define R_AARCH64_RELATIVE     1027	/* 按程序基址调整。  */
#define R_AARCH64_TLS_DTPMOD64 1028	/* 模块号，64 位。  */
#define R_AARCH64_TLS_DTPREL64 1029	/* 模块相对偏移，64 位。  */
#define R_AARCH64_TLS_TPREL64  1030	/* TP 相对偏移，64 位。  */
#define R_AARCH64_TLSDESC      1031	/* TLS 描述符。  */
#define R_AARCH64_IRELATIVE    1032	/* STT_GNU_IFUNC 重定位。  */
/* 保持此条目为最后一项。  */
#define R_AARCH64_NUM          1033

/* ARM 重定位。  */

#define R_ARM_NONE		0	/* 无重定位 */
#define R_ARM_PC24		1	/* PC 相对 26 位分支 */
#define R_ARM_ABS32		2	/* 直接 32 位  */
#define R_ARM_REL32		3	/* PC 相对 32 位 */
#define R_ARM_PC13		4
#define R_ARM_ABS16		5	/* 直接 16 位 */
#define R_ARM_ABS12		6	/* 直接 12 位 */
#define R_ARM_THM_ABS5		7
#define R_ARM_ABS8		8	/* 直接 8 位 */
#define R_ARM_SBREL32		9
#define R_ARM_THM_PC22		10
#define R_ARM_THM_PC8		11
#define R_ARM_AMP_VCALL9	12
#define R_ARM_SWI24		13	/* 已废弃的静态重定位。  */
#define R_ARM_TLS_DESC		13      /* 动态重定位。  */
#define R_ARM_THM_SWI8		14
#define R_ARM_XPC25		15
#define R_ARM_THM_XPC22		16
#define R_ARM_TLS_DTPMOD32	17	/* 含符号的模块的 ID */
#define R_ARM_TLS_DTPOFF32	18	/* TLS 块中的偏移 */
#define R_ARM_TLS_TPOFF32	19	/* 静态 TLS 块中的偏移 */
#define R_ARM_COPY		20	/* 运行时复制符号 */
#define R_ARM_GLOB_DAT		21	/* 创建 GOT 条目 */
#define R_ARM_JUMP_SLOT		22	/* 创建 PLT 条目 */
#define R_ARM_RELATIVE		23	/* 按程序基址调整 */
#define R_ARM_GOTOFF		24	/* 到 GOT 的 32 位偏移 */
#define R_ARM_GOTPC		25	/* 到 GOT 的 32 位 PC 相对偏移 */
#define R_ARM_GOT32		26	/* 32 位 GOT 条目 */
#define R_ARM_PLT32		27	/* 32 位 PLT 地址 */
#define R_ARM_CALL		28
#define R_ARM_JUMP24		29
#define R_ARM_THM_JUMP24	30
#define R_ARM_ALU_PCREL_7_0	32
#define R_ARM_ALU_PCREL_15_8	33
#define R_ARM_ALU_PCREL_23_15	34
#define R_ARM_LDR_SBREL_11_0	35
#define R_ARM_ALU_SBREL_19_12	36
#define R_ARM_ALU_SBREL_27_20	37
#define R_ARM_V4BX		40
#define R_ARM_PREL31		42
#define R_ARM_MOVW_ABS_NC	43
#define R_ARM_MOVT_ABS		 44
#define R_ARM_THM_MOVW_ABS_NC	47
#define R_ARM_THM_MOVT_ABS	48
#define R_ARM_TLS_GOTDESC	90
#define R_ARM_TLS_CALL		91
#define R_ARM_TLS_DESCSEQ	92
#define R_ARM_THM_TLS_CALL	93
#define R_ARM_GNU_VTENTRY	100
#define R_ARM_GNU_VTINHERIT	101
#define R_ARM_THM_PC11		102	/* thumb 无条件分支 */
#define R_ARM_THM_PC9		103	/* thumb 条件分支 */
#define R_ARM_TLS_GD32		104	/* 用于全局动态线程局部数据的 PC 相对 32
					   位 */
#define R_ARM_TLS_LDM32		105	/* 用于局部动态线程局部数据的 PC 相对 32
					   位 */
#define R_ARM_TLS_LDO32		106	/* 相对于 TLS 块的 32
					   位偏移 */
#define R_ARM_TLS_IE32		107	/* 用于静态 TLS 块偏移的 GOT 条目的 PC 相对 32
					   位 */
#define R_ARM_TLS_LE32		108	/* 相对于静态 TLS 块的 32
					   位偏移 */
#define	R_ARM_THM_TLS_DESCSEQ	129
#define R_ARM_IRELATIVE		160
#define R_ARM_RXPC25		249
#define R_ARM_RSBREL32		250
#define R_ARM_THM_RPC22		251
#define R_ARM_RREL32		252
#define R_ARM_RABS22		253
#define R_ARM_RPC24		254
#define R_ARM_RBASE		255
/* 保持此条目为最后一项。  */
#define R_ARM_NUM		256

/* TMS320C67xx 特有声明 */

/* XXX：尚无 ELF 标准*/

/* TMS320C67xx 重定位。 */
#define R_C60_32       1
#define R_C60_GOT32     3               /* 32 位 GOT 条目 */
#define R_C60_PLT32     4               /* 32 位 PLT 地址 */
#define R_C60_COPY      5               /* 运行时复制符号 */
#define R_C60_GLOB_DAT  6               /* 创建 GOT 条目 */
#define R_C60_JMP_SLOT  7               /* 创建 PLT 条目 */
#define R_C60_RELATIVE  8               /* 按程序基址调整 */
#define R_C60_GOTOFF    9               /* 到 GOT 的 32 位偏移 */
#define R_C60_GOTPC     10              /* 到 GOT 的 32 位 PC 相对偏移 */

#define R_C60LO16      0x54       /* 低 16 位 MVKL 嵌入 */
#define R_C60HI16      0x55       /* 高 16 位 MVKH 嵌入 */
/* 保持此条目为最后一项。  */
#define R_C60_NUM      0x56

/* IA-64 特定声明。  */

/* Ehdr e_flags 字段的处理器特定标志。  */
#define EF_IA_64_MASKOS		0x0000000f	/* 操作系统特定标志 */
#define EF_IA_64_ABI64		0x00000010	/* 64 位 ABI */
#define EF_IA_64_ARCH		0xff000000	/* 体系结构版本掩码 */

/* Phdr 的 p_type 字段的处理器特有值。  */
#define PT_IA_64_ARCHEXT	(PT_LOPROC + 0)	/* 体系结构扩展位 */
#define PT_IA_64_UNWIND		(PT_LOPROC + 1)	/* ia64 展开位 */
#define PT_IA_64_HP_OPT_ANOT	(PT_LOOS + 0x12)
#define PT_IA_64_HP_HSL_ANOT	(PT_LOOS + 0x13)
#define PT_IA_64_HP_STACK	(PT_LOOS + 0x14)

/* Phdr p_flags 字段的处理器特定标志。  */
#define PF_IA_64_NORECOV	0x80000000	/* 无恢复的推测指令 */

/* Shdr 的 sh_type 字段的处理器特有值。  */
#define SHT_IA_64_EXT		(SHT_LOPROC + 0) /* 扩展位 */
#define SHT_IA_64_UNWIND	(SHT_LOPROC + 1) /* 展开位 */

/* Shdr sh_flags 字段的处理器特定标志。  */
#define SHF_IA_64_SHORT		0x10000000	/* 靠近 gp 的段 */
#define SHF_IA_64_NORECOV	0x20000000	/* 无恢复的推测指令 */

/* Dyn d_tag 字段的处理器特定值。  */
#define DT_IA_64_PLT_RESERVE	(DT_LOPROC + 0)
#define DT_IA_64_NUM		1

/* IA-64 重定位。  */
#define R_IA64_NONE		0x00	/* 无 */
#define R_IA64_IMM14		0x21	/* 符号 + 加数，add imm14 */
#define R_IA64_IMM22		0x22	/* 符号 + 加数，add imm22 */
#define R_IA64_IMM64		0x23	/* 符号 + 加数，mov imm64 */
#define R_IA64_DIR32MSB		0x24	/* 符号 + 加数，data4 MSB */
#define R_IA64_DIR32LSB		0x25	/* 符号 + 加数，data4 LSB */
#define R_IA64_DIR64MSB		0x26	/* 符号 + 加数，data8 MSB */
#define R_IA64_DIR64LSB		0x27	/* 符号 + 加数，data8 LSB */
#define R_IA64_GPREL22		0x2a	/* @gprel(sym + add), add imm22 */
#define R_IA64_GPREL64I		0x2b	/* @gprel(sym + add), mov imm64 */
#define R_IA64_GPREL32MSB	0x2c	/* @gprel(sym + add), data4 MSB */
#define R_IA64_GPREL32LSB	0x2d	/* @gprel(sym + add), data4 LSB */
#define R_IA64_GPREL64MSB	0x2e	/* @gprel(sym + add), data8 MSB */
#define R_IA64_GPREL64LSB	0x2f	/* @gprel(sym + add), data8 LSB */
#define R_IA64_LTOFF22		0x32	/* @ltoff(sym + add), add imm22 */
#define R_IA64_LTOFF64I		0x33	/* @ltoff(sym + add), mov imm64 */
#define R_IA64_PLTOFF22		0x3a	/* @pltoff(sym + add), add imm22 */
#define R_IA64_PLTOFF64I	0x3b	/* @pltoff(sym + add), mov imm64 */
#define R_IA64_PLTOFF64MSB	0x3e	/* @pltoff(sym + add), data8 MSB */
#define R_IA64_PLTOFF64LSB	0x3f	/* @pltoff(sym + add), data8 LSB */
#define R_IA64_FPTR64I		0x43	/* @fptr(sym + add), mov imm64 */
#define R_IA64_FPTR32MSB	0x44	/* @fptr(sym + add), data4 MSB */
#define R_IA64_FPTR32LSB	0x45	/* @fptr(sym + add), data4 LSB */
#define R_IA64_FPTR64MSB	0x46	/* @fptr(sym + add), data8 MSB */
#define R_IA64_FPTR64LSB	0x47	/* @fptr(sym + add), data8 LSB */
#define R_IA64_PCREL60B		0x48	/* @pcrel(sym + add), brl */
#define R_IA64_PCREL21B		0x49	/* @pcrel(sym + add), ptb, call */
#define R_IA64_PCREL21M		0x4a	/* @pcrel(sym + add), chk.s */
#define R_IA64_PCREL21F		0x4b	/* @pcrel(sym + add), fchkf */
#define R_IA64_PCREL32MSB	0x4c	/* @pcrel(sym + add), data4 MSB */
#define R_IA64_PCREL32LSB	0x4d	/* @pcrel(sym + add), data4 LSB */
#define R_IA64_PCREL64MSB	0x4e	/* @pcrel(sym + add), data8 MSB */
#define R_IA64_PCREL64LSB	0x4f	/* @pcrel(sym + add), data8 LSB */
#define R_IA64_LTOFF_FPTR22	0x52	/* @ltoff(@fptr(s+a)), imm22 */
#define R_IA64_LTOFF_FPTR64I	0x53	/* @ltoff(@fptr(s+a)), imm64 */
#define R_IA64_LTOFF_FPTR32MSB	0x54	/* @ltoff(@fptr(s+a)), data4 MSB */
#define R_IA64_LTOFF_FPTR32LSB	0x55	/* @ltoff(@fptr(s+a)), data4 LSB */
#define R_IA64_LTOFF_FPTR64MSB	0x56	/* @ltoff(@fptr(s+a)), data8 MSB */
#define R_IA64_LTOFF_FPTR64LSB	0x57	/* @ltoff(@fptr(s+a)), data8 LSB */
#define R_IA64_SEGREL32MSB	0x5c	/* @segrel(sym + add), data4 MSB */
#define R_IA64_SEGREL32LSB	0x5d	/* @segrel(sym + add), data4 LSB */
#define R_IA64_SEGREL64MSB	0x5e	/* @segrel(sym + add), data8 MSB */
#define R_IA64_SEGREL64LSB	0x5f	/* @segrel(sym + add), data8 LSB */
#define R_IA64_SECREL32MSB	0x64	/* @secrel(sym + add), data4 MSB */
#define R_IA64_SECREL32LSB	0x65	/* @secrel(sym + add), data4 LSB */
#define R_IA64_SECREL64MSB	0x66	/* @secrel(sym + add), data8 MSB */
#define R_IA64_SECREL64LSB	0x67	/* @secrel(sym + add), data8 LSB */
#define R_IA64_REL32MSB		0x6c	/* data 4 + REL */
#define R_IA64_REL32LSB		0x6d	/* data 4 + REL */
#define R_IA64_REL64MSB		0x6e	/* data 8 + REL */
#define R_IA64_REL64LSB		0x6f	/* data 8 + REL */
#define R_IA64_LTV32MSB		0x74	/* 符号 + 加数，data4 MSB */
#define R_IA64_LTV32LSB		0x75	/* 符号 + 加数，data4 LSB */
#define R_IA64_LTV64MSB		0x76	/* 符号 + 加数，data8 MSB */
#define R_IA64_LTV64LSB		0x77	/* 符号 + 加数，data8 LSB */
#define R_IA64_PCREL21BI	0x79	/* @pcrel(sym + add), 21bit inst */
#define R_IA64_PCREL22		0x7a	/* @pcrel(sym + add), 22bit inst */
#define R_IA64_PCREL64I		0x7b	/* @pcrel(sym + add), 64bit inst */
#define R_IA64_IPLTMSB		0x80	/* 动态重定位，导入的 PLT，MSB */
#define R_IA64_IPLTLSB		0x81	/* 动态重定位，导入的 PLT，LSB */
#define R_IA64_COPY		0x84	/* 复制重定位 */
#define R_IA64_SUB		0x85	/* 加数与符号之差 */
#define R_IA64_LTOFF22X		0x86	/* LTOFF22，可松弛。  */
#define R_IA64_LDXMOV		0x87	/* LTOFF22X 的使用。  */
#define R_IA64_TPREL14		0x91	/* @tprel(sym + add), imm14 */
#define R_IA64_TPREL22		0x92	/* @tprel(sym + add), imm22 */
#define R_IA64_TPREL64I		0x93	/* @tprel(sym + add), imm64 */
#define R_IA64_TPREL64MSB	0x96	/* @tprel(sym + add), data8 MSB */
#define R_IA64_TPREL64LSB	0x97	/* @tprel(sym + add), data8 LSB */
#define R_IA64_LTOFF_TPREL22	0x9a	/* @ltoff(@tprel(s+a)), imm2 */
#define R_IA64_DTPMOD64MSB	0xa6	/* @dtpmod(sym + add), data8 MSB */
#define R_IA64_DTPMOD64LSB	0xa7	/* @dtpmod(sym + add), data8 LSB */
#define R_IA64_LTOFF_DTPMOD22	0xaa	/* @ltoff(@dtpmod(sym + add)), imm22 */
#define R_IA64_DTPREL14		0xb1	/* @dtprel(sym + add), imm14 */
#define R_IA64_DTPREL22		0xb2	/* @dtprel(sym + add), imm22 */
#define R_IA64_DTPREL64I	0xb3	/* @dtprel(sym + add), imm64 */
#define R_IA64_DTPREL32MSB	0xb4	/* @dtprel(sym + add), data4 MSB */
#define R_IA64_DTPREL32LSB	0xb5	/* @dtprel(sym + add), data4 LSB */
#define R_IA64_DTPREL64MSB	0xb6	/* @dtprel(sym + add), data8 MSB */
#define R_IA64_DTPREL64LSB	0xb7	/* @dtprel(sym + add), data8 LSB */
#define R_IA64_LTOFF_DTPREL22	0xba	/* @ltoff(@dtprel(s+a)), imm22 */

/* SH 特定声明 */

/* ELF 头 e_flags 字段的处理器特有标志。  */
#define EF_SH_MACH_MASK		0x1f
#define EF_SH_UNKNOWN		0x0
#define EF_SH1			0x1
#define EF_SH2			0x2
#define EF_SH3			0x3
#define EF_SH_DSP		0x4
#define EF_SH3_DSP		0x5
#define EF_SH4AL_DSP		0x6
#define EF_SH3E			0x8
#define EF_SH4			0x9
#define EF_SH2E			0xb
#define EF_SH4A			0xc
#define EF_SH2A			0xd
#define EF_SH4_NOFPU		0x10
#define EF_SH4A_NOFPU		0x11
#define EF_SH4_NOMMU_NOFPU	0x12
#define EF_SH2A_NOFPU		0x13
#define EF_SH3_NOMMU		0x14
#define EF_SH2A_SH4_NOFPU	0x15
#define EF_SH2A_SH3_NOFPU	0x16
#define EF_SH2A_SH4		0x17
#define EF_SH2A_SH3E		0x18

/* SH 重定位。  */
#define	R_SH_NONE		0
#define	R_SH_DIR32		1
#define	R_SH_REL32		2
#define	R_SH_DIR8WPN		3
#define	R_SH_IND12W		4
#define	R_SH_DIR8WPL		5
#define	R_SH_DIR8WPZ		6
#define	R_SH_DIR8BP		7
#define	R_SH_DIR8W		8
#define	R_SH_DIR8L		9
#define	R_SH_SWITCH16		25
#define	R_SH_SWITCH32		26
#define	R_SH_USES		27
#define	R_SH_COUNT		28
#define	R_SH_ALIGN		29
#define	R_SH_CODE		30
#define	R_SH_DATA		31
#define	R_SH_LABEL		32
#define	R_SH_SWITCH8		33
#define	R_SH_GNU_VTINHERIT	34
#define	R_SH_GNU_VTENTRY	35
#define	R_SH_TLS_GD_32		144
#define	R_SH_TLS_LD_32		145
#define	R_SH_TLS_LDO_32		146
#define	R_SH_TLS_IE_32		147
#define	R_SH_TLS_LE_32		148
#define	R_SH_TLS_DTPMOD32	149
#define	R_SH_TLS_DTPOFF32	150
#define	R_SH_TLS_TPOFF32	151
#define	R_SH_GOT32		160
#define	R_SH_PLT32		161
#define	R_SH_COPY		162
#define	R_SH_GLOB_DAT		163
#define	R_SH_JMP_SLOT		164
#define	R_SH_RELATIVE		165
#define	R_SH_GOTOFF		166
#define	R_SH_GOTPC		167
/* 保持此条目为最后一项。  */
#define	R_SH_NUM		256

/* S/390 特定定义。  */

/* e_flags 字段的有效值。  */

#define EF_S390_HIGH_GPRS    0x00000001  /* 需要高 GPR 内核功能。  */

/* 附加的 s390 重定位 */

#define R_390_NONE		0	/* 无重定位。  */
#define R_390_8			1	/* 直接 8 位。  */
#define R_390_12		2	/* 直接 12 位。  */
#define R_390_16		3	/* 直接 16 位。  */
#define R_390_32		4	/* 直接 32 位。  */
#define R_390_PC32		5	/* PC 相对 32 位。	*/
#define R_390_GOT12		6	/* 12 位 GOT 偏移。  */
#define R_390_GOT32		7	/* 32 位 GOT 偏移。  */
#define R_390_PLT32		8	/* 32 位 PC 相对 PLT 地址。  */
#define R_390_COPY		9	/* 在运行时复制符号。  */
#define R_390_GLOB_DAT		10	/* 创建 GOT 条目。  */
#define R_390_JMP_SLOT		11	/* 创建 PLT 条目。  */
#define R_390_RELATIVE		12	/* 按程序基址调整。  */
#define R_390_GOTOFF32		13	/* 到 GOT 的 32 位偏移。	 */
#define R_390_GOTPC		14	/* 到 GOT 的 32 位 PC 相对偏移。  */
#define R_390_GOT16		15	/* 16 位 GOT 偏移。  */
#define R_390_PC16		16	/* PC 相对 16 位。	*/
#define R_390_PC16DBL		17	/* 左移 1 位的 PC 相对 16 位。  */
#define R_390_PLT16DBL		18	/* 左移 1 位的 16 位 PC 相对 PLT。  */
#define R_390_PC32DBL		19	/* 左移 1 位的 PC 相对 32 位。  */
#define R_390_PLT32DBL		20	/* 左移 1 位的 32 位 PC 相对 PLT。  */
#define R_390_GOTPCDBL		21	/* 左移 1 位的 32 位 PC 相对 GOT。  */
#define R_390_64		22	/* 直接 64 位。  */
#define R_390_PC64		23	/* PC 相对 64 位。	*/
#define R_390_GOT64		24	/* 64 位 GOT 偏移。  */
#define R_390_PLT64		25	/* 64 位 PC 相对 PLT 地址。  */
#define R_390_GOTENT		26	/* 到 GOT 条目的 32 位 PC 相对 >> 1。 */
#define R_390_GOTOFF16		27	/* 到 GOT 的 16 位偏移。 */
#define R_390_GOTOFF64		28	/* 到 GOT 的 64 位偏移。 */
#define R_390_GOTPLT12		29	/* 到跳转槽的 12 位偏移。	*/
#define R_390_GOTPLT16		30	/* 到跳转槽的 16 位偏移。	*/
#define R_390_GOTPLT32		31	/* 到跳转槽的 32 位偏移。	*/
#define R_390_GOTPLT64		32	/* 到跳转槽的 64 位偏移。	*/
#define R_390_GOTPLTENT		33	/* 到跳转槽的 32 位相对偏移。  */
#define R_390_PLTOFF16		34	/* 从 GOT 到 PLT 的 16 位偏移。 */
#define R_390_PLTOFF32		35	/* 从 GOT 到 PLT 的 32 位偏移。 */
#define R_390_PLTOFF64		36	/* 从 GOT 到 PLT 的 16 位偏移。 */
#define R_390_TLS_LOAD		37	/* TLS 代码中加载指令的标记。  */
#define R_390_TLS_GDCALL	38	/* 通用动态 TLS
					   代码中函数调用的标记。 */
#define R_390_TLS_LDCALL	39	/* 本地动态 TLS
					   代码中函数调用的标记。 */
#define R_390_TLS_GD32		40	/* 通用动态线程局部数据的直接 32
					   位。  */
#define R_390_TLS_GD64		41	/* 通用动态线程局部数据的直接 64
					  位。  */
#define R_390_TLS_GOTIE12	42	/* 静态 TLS 块偏移的 12 位 GOT
					   偏移。  */
#define R_390_TLS_GOTIE32	43	/* 静态 TLS 块偏移的 32 位 GOT
					   偏移。  */
#define R_390_TLS_GOTIE64	44	/* 静态 TLS 块偏移的 64 位 GOT
					   偏移。 */
#define R_390_TLS_LDM32		45	/* LE 代码中本地动态线程局部数据的直接 32
					   位。  */
#define R_390_TLS_LDM64		46	/* LE 代码中本地动态线程局部数据的直接 64
					   位。  */
#define R_390_TLS_IE32		47	/* 被取反的静态 TLS 块偏移的 GOT 条目 32
					   位地址。  */
#define R_390_TLS_IE64		48	/* 被取反的静态 TLS 块偏移的 GOT 条目 64
					   位地址。  */
#define R_390_TLS_IEENT		49	/* 被取反的静态 TLS 块偏移的 GOT 条目 32
					   位相对偏移。  */
#define R_390_TLS_LE32		50	/* 相对于静态 TLS 块的 32
					   位取反偏移。  */
#define R_390_TLS_LE64		51	/* 相对于静态 TLS 块的 64
					   位取反偏移。  */
#define R_390_TLS_LDO32		52	/* 相对于 TLS 块的 32
					   位偏移。  */
#define R_390_TLS_LDO64		53	/* 相对于 TLS 块的 64
					   位偏移。  */
#define R_390_TLS_DTPMOD	54	/* 包含符号的模块 ID。  */
#define R_390_TLS_DTPOFF	55	/* TLS 块中的偏移。	 */
#define R_390_TLS_TPOFF		56	/* 静态 TLS
					   块中的取反偏移。  */
#define R_390_20		57	/* 直接 20 位。  */
#define R_390_GOT20		58	/* 20 位 GOT 偏移。  */
#define R_390_GOTPLT20		59	/* 到跳转槽的 20 位偏移。  */
#define R_390_TLS_GOTIE20	60	/* 静态 TLS 块偏移的 20 位 GOT
					   偏移。  */
#define R_390_IRELATIVE         61      /* STT_GNU_IFUNC 重定位。  */
/* 保持此条目为最后一项。  */
#define R_390_NUM		62


/* CRIS 重定位。  */
#define R_CRIS_NONE		0
#define R_CRIS_8		1
#define R_CRIS_16		2
#define R_CRIS_32		3
#define R_CRIS_8_PCREL		4
#define R_CRIS_16_PCREL		5
#define R_CRIS_32_PCREL		6
#define R_CRIS_GNU_VTINHERIT	7
#define R_CRIS_GNU_VTENTRY	8
#define R_CRIS_COPY		9
#define R_CRIS_GLOB_DAT		10
#define R_CRIS_JUMP_SLOT	11
#define R_CRIS_RELATIVE		12
#define R_CRIS_16_GOT		13
#define R_CRIS_32_GOT		14
#define R_CRIS_16_GOTPLT	15
#define R_CRIS_32_GOTPLT	16
#define R_CRIS_32_GOTREL	17
#define R_CRIS_32_PLT_GOTREL	18
#define R_CRIS_32_PLT_PCREL	19

#define R_CRIS_NUM		20


/* AMD x86-64 重定位。  */
#define R_X86_64_NONE		0	/* 无重定位 */
#define R_X86_64_64		1	/* 直接 64 位  */
#define R_X86_64_PC32		2	/* PC 相对 32 位有符号 */
#define R_X86_64_GOT32		3	/* 32 位 GOT 条目 */
#define R_X86_64_PLT32		4	/* 32 位 PLT 地址 */
#define R_X86_64_COPY		5	/* 运行时复制符号 */
#define R_X86_64_GLOB_DAT	6	/* 创建 GOT 条目 */
#define R_X86_64_JUMP_SLOT	7	/* 创建 PLT 条目 */
#define R_X86_64_RELATIVE	8	/* 按程序基址调整 */
#define R_X86_64_GOTPCREL	9	/* 到 GOT 的 32 位有符号 PC
					   相对偏移 */
#define R_X86_64_32		10	/* 直接 32 位零扩展 */
#define R_X86_64_32S		11	/* 直接 32 位符号扩展 */
#define R_X86_64_16		12	/* 直接 16 位零扩展 */
#define R_X86_64_PC16		13	/* 16 位符号扩展 PC 相对 */
#define R_X86_64_8		14	/* 直接 8 位符号扩展  */
#define R_X86_64_PC8		15	/* 8 位符号扩展 PC 相对 */
#define R_X86_64_DTPMOD64	16	/* 含符号的模块的 ID */
#define R_X86_64_DTPOFF64	17	/* 模块 TLS 块中的偏移 */
#define R_X86_64_TPOFF64	18	/* 初始 TLS 块中的偏移 */
#define R_X86_64_TLSGD		19	/* 到 GD 符号的两个 GOT 条目的 32 位有符号 PC
					   相对偏移 */
#define R_X86_64_TLSLD		20	/* 到 LD 符号的两个 GOT 条目的 32 位有符号 PC
					   相对偏移 */
#define R_X86_64_DTPOFF32	21	/* TLS 块中的偏移 */
#define R_X86_64_GOTTPOFF	22	/* 到 IE 符号的 GOT 条目的 32 位有符号 PC
					   相对偏移 */
#define R_X86_64_TPOFF32	23	/* 初始 TLS 块中的偏移 */
#define R_X86_64_PC64		24	/* PC 相对 64 位 */
#define R_X86_64_GOTOFF64	25	/* 到 GOT 的 64 位偏移 */
#define R_X86_64_GOTPC32	26	/* 到 GOT 的 32 位有符号 PC
					   相对偏移 */
#define R_X86_64_GOT64		27	/* 64 位 GOT 条目偏移 */
#define R_X86_64_GOTPCREL64	28	/* 到 GOT 条目的 64 位 PC
					   相对偏移 */
#define R_X86_64_GOTPC64	29	/* 到 GOT 的 64 位 PC 相对偏移 */
#define R_X86_64_GOTPLT64	30 	/* 类似 GOT64，表示需要 PLT 条目 */
#define R_X86_64_PLTOFF64	31	/* 到 PLT 条目的 64 位 GOT
					   相对偏移 */
#define R_X86_64_SIZE32		32	/* 符号大小加 32 位加数 */
#define R_X86_64_SIZE64		33	/* 符号大小加 64 位加数 */
#define R_X86_64_GOTPC32_TLSDESC 34	/* TLS 描述符的 GOT 偏移。  */
#define R_X86_64_TLSDESC_CALL   35	/* 通过 TLS
					   描述符调用的标记。  */
#define R_X86_64_TLSDESC        36	/* TLS 描述符。  */
#define R_X86_64_IRELATIVE	37	/* 按程序基址间接调整 */
#define R_X86_64_RELATIVE64	38	/* 按程序基址的 64 位调整 */
#define R_X86_64_GOTPCRELX	41	/* 类似
					   GOTPCREL，但可选地带有链接器优化 */
#define R_X86_64_REX_GOTPCRELX	42      /* 类似 GOTPCRELX，但存在 REX
					   前缀 */

#define R_X86_64_NUM		43


/* AM33 重定位。  */
#define R_MN10300_NONE		0	/* 无重定位。  */
#define R_MN10300_32		1	/* 直接 32 位。  */
#define R_MN10300_16		2	/* 直接 16 位。  */
#define R_MN10300_8		3	/* 直接 8 位。  */
#define R_MN10300_PCREL32	4	/* PC 相对 32 位。  */
#define R_MN10300_PCREL16	5	/* PC 相对 16 位有符号。  */
#define R_MN10300_PCREL8	6	/* PC 相对 8 位有符号。  */
#define R_MN10300_GNU_VTINHERIT	7	/* 古老的 C++ vtable 垃圾... */
#define R_MN10300_GNU_VTENTRY	8	/* ... 收集标注。  */
#define R_MN10300_24		9	/* 直接 24 位。  */
#define R_MN10300_GOTPC32	10	/* 到 GOT 的 32 位 PC 相对偏移。  */
#define R_MN10300_GOTPC16	11	/* 到 GOT 的 16 位 PC 相对偏移。  */
#define R_MN10300_GOTOFF32	12	/* 来自 GOT 的 32 位偏移。  */
#define R_MN10300_GOTOFF24	13	/* 来自 GOT 的 24 位偏移。  */
#define R_MN10300_GOTOFF16	14	/* 来自 GOT 的 16 位偏移。  */
#define R_MN10300_PLT32		15	/* 到 PLT 条目的 32 位 PC 相对。  */
#define R_MN10300_PLT16		16	/* 到 PLT 条目的 16 位 PC 相对。  */
#define R_MN10300_GOT32		17	/* 到 GOT 条目的 32 位偏移。  */
#define R_MN10300_GOT24		18	/* 到 GOT 条目的 24 位偏移。  */
#define R_MN10300_GOT16		19	/* 到 GOT 条目的 16 位偏移。  */
#define R_MN10300_COPY		20	/* 在运行时复制符号。  */
#define R_MN10300_GLOB_DAT	21	/* 创建 GOT 条目。  */
#define R_MN10300_JMP_SLOT	22	/* 创建 PLT 条目。  */
#define R_MN10300_RELATIVE	23	/* 按程序基址调整。  */
#define R_MN10300_TLS_GD	24	/* 全局动态的 32 位偏移。  */
#define R_MN10300_TLS_LD	25	/* 本地动态的 32 位偏移。  */
#define R_MN10300_TLS_LDO	26	/* 模块相对偏移。  */
#define R_MN10300_TLS_GOTIE	27	/* 静态 TLS 块偏移的 GOT
					   偏移。  */
#define R_MN10300_TLS_IE	28	/* 静态 TLS 块偏移的 GOT
					   地址。  */
#define R_MN10300_TLS_LE	29	/* 相对于静态 TLS
					   块的偏移。  */
#define R_MN10300_TLS_DTPMOD	30	/* 包含符号的模块 ID。  */
#define R_MN10300_TLS_DTPOFF	31	/* 模块 TLS 块中的偏移。  */
#define R_MN10300_TLS_TPOFF	32	/* 静态 TLS 块中的偏移。  */
#define R_MN10300_SYM_DIFF	33	/*
					   链接器松弛所需的下一个重定位调整。  */
#define R_MN10300_ALIGN		34	/*
					   链接器松弛的对齐要求。  */
#define R_MN10300_NUM		35


/* M32R 重定位。  */
#define R_M32R_NONE		0	/* 无重定位。 */
#define R_M32R_16		1	/* 直接 16 位。 */
#define R_M32R_32		2	/* 直接 32 位。 */
#define R_M32R_24		3	/* 直接 24 位。 */
#define R_M32R_10_PCREL		4	/* PC 相对 10 位已移位。 */
#define R_M32R_18_PCREL		5	/* PC 相对 18 位已移位。 */
#define R_M32R_26_PCREL		6	/* PC 相对 26 位已移位。 */
#define R_M32R_HI16_ULO		7	/* 高 16 位，低端无符号。 */
#define R_M32R_HI16_SLO		8	/* 高 16 位，低端有符号。 */
#define R_M32R_LO16		9	/* 低 16 位。 */
#define R_M32R_SDA16		10	/* SDA 中的 16 位偏移。 */
#define R_M32R_GNU_VTINHERIT	11
#define R_M32R_GNU_VTENTRY	12
/* M32R 重定位使用 SHT_RELA。  */
#define R_M32R_16_RELA		33	/* 直接 16 位。 */
#define R_M32R_32_RELA		34	/* 直接 32 位。 */
#define R_M32R_24_RELA		35	/* 直接 24 位。 */
#define R_M32R_10_PCREL_RELA	36	/* PC 相对 10 位已移位。 */
#define R_M32R_18_PCREL_RELA	37	/* PC 相对 18 位已移位。 */
#define R_M32R_26_PCREL_RELA	38	/* PC 相对 26 位已移位。 */
#define R_M32R_HI16_ULO_RELA	39	/* 高 16 位，低端无符号 */
#define R_M32R_HI16_SLO_RELA	40	/* 高 16 位，低端有符号 */
#define R_M32R_LO16_RELA	41	/* 低 16 位 */
#define R_M32R_SDA16_RELA	42	/* SDA 中的 16 位偏移 */
#define R_M32R_RELA_GNU_VTINHERIT	43
#define R_M32R_RELA_GNU_VTENTRY	44
#define R_M32R_REL32		45	/* PC 相对 32 位。  */

#define R_M32R_GOT24		48	/* 24 位 GOT 条目 */
#define R_M32R_26_PLTREL	49	/* 左移的到 PLT 的 26 位 PC 相对 */
#define R_M32R_COPY		50	/* 运行时复制符号 */
#define R_M32R_GLOB_DAT		51	/* 创建 GOT 条目 */
#define R_M32R_JMP_SLOT		52	/* 创建 PLT 条目 */
#define R_M32R_RELATIVE		53	/* 按程序基址调整 */
#define R_M32R_GOTOFF		54	/* 到 GOT 的 24 位偏移 */
#define R_M32R_GOTPC24		55	/* 到 GOT 的 24 位 PC 相对偏移 */
#define R_M32R_GOT16_HI_ULO	56	/* 低端无符号的高 16 位 GOT
					   条目 */
#define R_M32R_GOT16_HI_SLO	57	/* 低端有符号的高 16 位 GOT
					   条目 */
#define R_M32R_GOT16_LO		58	/* 低 16 位 GOT 条目 */
#define R_M32R_GOTPC_HI_ULO	59	/* 带无符号低端的到 GOT 的高 16 位 PC
					   相对偏移 */
#define R_M32R_GOTPC_HI_SLO	60	/* 带有符号低端的到 GOT 的高 16 位 PC
					   相对偏移 */
#define R_M32R_GOTPC_LO		61	/* 到 GOT 的低 16 位 PC
					   相对偏移 */
#define R_M32R_GOTOFF_HI_ULO	62	/* 带无符号低端的到 GOT 的高 16
					   位偏移 */
#define R_M32R_GOTOFF_HI_SLO	63	/* 带有符号低端的到 GOT 的高 16
					   位偏移 */
#define R_M32R_GOTOFF_LO	64	/* 到 GOT 的低 16 位偏移 */
#define R_M32R_NUM		256	/* 保持此项为最后一条。 */


/* TILEPro 重定位。  */
#define R_TILEPRO_NONE		0	/* 无重定位 */
#define R_TILEPRO_32		1	/* 直接 32 位 */
#define R_TILEPRO_16		2	/* 直接 16 位 */
#define R_TILEPRO_8		3	/* 直接 8 位 */
#define R_TILEPRO_32_PCREL	4	/* PC 相对 32 位 */
#define R_TILEPRO_16_PCREL	5	/* PC 相对 16 位 */
#define R_TILEPRO_8_PCREL	6	/* PC 相对 8 位 */
#define R_TILEPRO_LO16		7	/* 低 16 位 */
#define R_TILEPRO_HI16		8	/* 高 16 位 */
#define R_TILEPRO_HA16		9	/* 高 16 位，已调整 */
#define R_TILEPRO_COPY		10	/* 复制重定位 */
#define R_TILEPRO_GLOB_DAT	11	/* 创建 GOT 条目 */
#define R_TILEPRO_JMP_SLOT	12	/* 创建 PLT 条目 */
#define R_TILEPRO_RELATIVE	13	/* 按程序基址调整 */
#define R_TILEPRO_BROFF_X1	14	/* X1 流水线分支偏移 */
#define R_TILEPRO_JOFFLONG_X1	15	/* X1 流水线跳转偏移 */
#define R_TILEPRO_JOFFLONG_X1_PLT 16	/* X1 流水线到 PLT 的跳转偏移 */
#define R_TILEPRO_IMM8_X0	17	/* X0 流水线 8 位 */
#define R_TILEPRO_IMM8_Y0	18	/* Y0 流水线 8 位 */
#define R_TILEPRO_IMM8_X1	19	/* X1 流水线 8 位 */
#define R_TILEPRO_IMM8_Y1	20	/* Y1 流水线 8 位 */
#define R_TILEPRO_MT_IMM15_X1	21	/* X1 流水线 mtspr */
#define R_TILEPRO_MF_IMM15_X1	22	/* X1 流水线 mfspr */
#define R_TILEPRO_IMM16_X0	23	/* X0 流水线 16 位 */
#define R_TILEPRO_IMM16_X1	24	/* X1 流水线 16 位 */
#define R_TILEPRO_IMM16_X0_LO	25	/* X0 流水线低 16 位 */
#define R_TILEPRO_IMM16_X1_LO	26	/* X1 流水线低 16 位 */
#define R_TILEPRO_IMM16_X0_HI	27	/* X0 流水线高 16 位 */
#define R_TILEPRO_IMM16_X1_HI	28	/* X1 流水线高 16 位 */
#define R_TILEPRO_IMM16_X0_HA	29	/* X0 流水线高 16 位，已调整 */
#define R_TILEPRO_IMM16_X1_HA	30	/* X1 流水线高 16 位，已调整 */
#define R_TILEPRO_IMM16_X0_PCREL 31	/* X0 流水线 PC 相对 16 位 */
#define R_TILEPRO_IMM16_X1_PCREL 32	/* X1 流水线 PC 相对 16 位 */
#define R_TILEPRO_IMM16_X0_LO_PCREL 33	/* X0 流水线 PC 相对低 16 位 */
#define R_TILEPRO_IMM16_X1_LO_PCREL 34	/* X1 流水线 PC 相对低 16 位 */
#define R_TILEPRO_IMM16_X0_HI_PCREL 35	/* X0 流水线 PC 相对高 16 位 */
#define R_TILEPRO_IMM16_X1_HI_PCREL 36	/* X1 流水线 PC 相对高 16 位 */
#define R_TILEPRO_IMM16_X0_HA_PCREL 37	/* X0 流水线 PC 相对 ha() 16 位 */
#define R_TILEPRO_IMM16_X1_HA_PCREL 38	/* X1 流水线 PC 相对 ha() 16 位 */
#define R_TILEPRO_IMM16_X0_GOT	39	/* X0 流水线 16 位 GOT 偏移 */
#define R_TILEPRO_IMM16_X1_GOT	40	/* X1 流水线 16 位 GOT 偏移 */
#define R_TILEPRO_IMM16_X0_GOT_LO 41	/* X0 流水线低 16 位 GOT 偏移 */
#define R_TILEPRO_IMM16_X1_GOT_LO 42	/* X1 流水线低 16 位 GOT 偏移 */
#define R_TILEPRO_IMM16_X0_GOT_HI 43	/* X0 流水线高 16 位 GOT 偏移 */
#define R_TILEPRO_IMM16_X1_GOT_HI 44	/* X1 流水线高 16 位 GOT 偏移 */
#define R_TILEPRO_IMM16_X0_GOT_HA 45	/* X0 流水线 ha() 16 位 GOT 偏移 */
#define R_TILEPRO_IMM16_X1_GOT_HA 46	/* X1 流水线 ha() 16 位 GOT 偏移 */
#define R_TILEPRO_MMSTART_X0	47	/* X0 流水线 mm "start" */
#define R_TILEPRO_MMEND_X0	48	/* X0 流水线 mm "end" */
#define R_TILEPRO_MMSTART_X1	49	/* X1 流水线 mm "start" */
#define R_TILEPRO_MMEND_X1	50	/* X1 流水线 mm "end" */
#define R_TILEPRO_SHAMT_X0	51	/* X0 流水线移位量 */
#define R_TILEPRO_SHAMT_X1	52	/* X1 流水线移位量 */
#define R_TILEPRO_SHAMT_Y0	53	/* Y0 流水线移位量 */
#define R_TILEPRO_SHAMT_Y1	54	/* Y1 流水线移位量 */
#define R_TILEPRO_DEST_IMM8_X1	55	/* X1 流水线目的 8 位 */
/* 重定位 56-59 目前未定义。  */
#define R_TILEPRO_TLS_GD_CALL	60	/* TLS GD 的 "jal" */
#define R_TILEPRO_IMM8_X0_TLS_GD_ADD 61	/* X0 流水线 TLS GD 的 "addi" */
#define R_TILEPRO_IMM8_X1_TLS_GD_ADD 62	/* X1 流水线 TLS GD 的 "addi" */
#define R_TILEPRO_IMM8_Y0_TLS_GD_ADD 63	/* Y0 流水线 TLS GD 的 "addi" */
#define R_TILEPRO_IMM8_Y1_TLS_GD_ADD 64	/* Y1 流水线 TLS GD 的 "addi" */
#define R_TILEPRO_TLS_IE_LOAD	65	/* TLS IE 的 "lw_tls" */
#define R_TILEPRO_IMM16_X0_TLS_GD 66	/* X0 流水线 16 位 TLS GD 偏移 */
#define R_TILEPRO_IMM16_X1_TLS_GD 67	/* X1 流水线 16 位 TLS GD 偏移 */
#define R_TILEPRO_IMM16_X0_TLS_GD_LO 68	/* X0 流水线低 16 位 TLS GD 偏移 */
#define R_TILEPRO_IMM16_X1_TLS_GD_LO 69	/* X1 流水线低 16 位 TLS GD 偏移 */
#define R_TILEPRO_IMM16_X0_TLS_GD_HI 70	/* X0 流水线高 16 位 TLS GD 偏移 */
#define R_TILEPRO_IMM16_X1_TLS_GD_HI 71	/* X1 流水线高 16 位 TLS GD 偏移 */
#define R_TILEPRO_IMM16_X0_TLS_GD_HA 72	/* X0 流水线 ha() 16 位 TLS GD 偏移 */
#define R_TILEPRO_IMM16_X1_TLS_GD_HA 73	/* X1 流水线 ha() 16 位 TLS GD 偏移 */
#define R_TILEPRO_IMM16_X0_TLS_IE 74	/* X0 流水线 16 位 TLS IE 偏移 */
#define R_TILEPRO_IMM16_X1_TLS_IE 75	/* X1 流水线 16 位 TLS IE 偏移 */
#define R_TILEPRO_IMM16_X0_TLS_IE_LO 76	/* X0 流水线低 16 位 TLS IE 偏移 */
#define R_TILEPRO_IMM16_X1_TLS_IE_LO 77	/* X1 流水线低 16 位 TLS IE 偏移 */
#define R_TILEPRO_IMM16_X0_TLS_IE_HI 78	/* X0 流水线高 16 位 TLS IE 偏移 */
#define R_TILEPRO_IMM16_X1_TLS_IE_HI 79	/* X1 流水线高 16 位 TLS IE 偏移 */
#define R_TILEPRO_IMM16_X0_TLS_IE_HA 80	/* X0 流水线 ha() 16 位 TLS IE 偏移 */
#define R_TILEPRO_IMM16_X1_TLS_IE_HA 81	/* X1 流水线 ha() 16 位 TLS IE 偏移 */
#define R_TILEPRO_TLS_DTPMOD32	82	/* 含符号的模块的 ID */
#define R_TILEPRO_TLS_DTPOFF32	83	/* TLS 块中的偏移 */
#define R_TILEPRO_TLS_TPOFF32	84	/* 静态 TLS 块中的偏移 */
#define R_TILEPRO_IMM16_X0_TLS_LE 85	/* X0 流水线 16 位 TLS LE 偏移 */
#define R_TILEPRO_IMM16_X1_TLS_LE 86	/* X1 流水线 16 位 TLS LE 偏移 */
#define R_TILEPRO_IMM16_X0_TLS_LE_LO 87	/* X0 流水线低 16 位 TLS LE 偏移 */
#define R_TILEPRO_IMM16_X1_TLS_LE_LO 88	/* X1 流水线低 16 位 TLS LE 偏移 */
#define R_TILEPRO_IMM16_X0_TLS_LE_HI 89	/* X0 流水线高 16 位 TLS LE 偏移 */
#define R_TILEPRO_IMM16_X1_TLS_LE_HI 90	/* X1 流水线高 16 位 TLS LE 偏移 */
#define R_TILEPRO_IMM16_X0_TLS_LE_HA 91	/* X0 流水线 ha() 16 位 TLS LE 偏移 */
#define R_TILEPRO_IMM16_X1_TLS_LE_HA 92	/* X1 流水线 ha() 16 位 TLS LE 偏移 */

#define R_TILEPRO_GNU_VTINHERIT	128	/* GNU C++ vtable 层次结构 */
#define R_TILEPRO_GNU_VTENTRY	129	/* GNU C++ vtable 成员用法 */

#define R_TILEPRO_NUM		130


/* TILE-Gx 重定位。  */
#define R_TILEGX_NONE		0	/* 无重定位 */
#define R_TILEGX_64		1	/* 直接 64 位 */
#define R_TILEGX_32		2	/* 直接 32 位 */
#define R_TILEGX_16		3	/* 直接 16 位 */
#define R_TILEGX_8		4	/* 直接 8 位 */
#define R_TILEGX_64_PCREL	5	/* PC 相对 64 位 */
#define R_TILEGX_32_PCREL	6	/* PC 相对 32 位 */
#define R_TILEGX_16_PCREL	7	/* PC 相对 16 位 */
#define R_TILEGX_8_PCREL	8	/* PC 相对 8 位 */
#define R_TILEGX_HW0		9	/* hword 0 16 位 */
#define R_TILEGX_HW1		10	/* hword 1 16 位 */
#define R_TILEGX_HW2		11	/* hword 2 16 位 */
#define R_TILEGX_HW3		12	/* hword 3 16 位 */
#define R_TILEGX_HW0_LAST	13	/* 最后 hword 0 16 位 */
#define R_TILEGX_HW1_LAST	14	/* 最后 hword 1 16 位 */
#define R_TILEGX_HW2_LAST	15	/* 最后 hword 2 16 位 */
#define R_TILEGX_COPY		16	/* 复制重定位 */
#define R_TILEGX_GLOB_DAT	17	/* 创建 GOT 条目 */
#define R_TILEGX_JMP_SLOT	18	/* 创建 PLT 条目 */
#define R_TILEGX_RELATIVE	19	/* 按程序基址调整 */
#define R_TILEGX_BROFF_X1	20	/* X1 流水线分支偏移 */
#define R_TILEGX_JUMPOFF_X1	21	/* X1 流水线跳转偏移 */
#define R_TILEGX_JUMPOFF_X1_PLT	22	/* X1 流水线到 PLT 的跳转偏移 */
#define R_TILEGX_IMM8_X0	23	/* X0 流水线 8 位 */
#define R_TILEGX_IMM8_Y0	24	/* Y0 流水线 8 位 */
#define R_TILEGX_IMM8_X1	25	/* X1 流水线 8 位 */
#define R_TILEGX_IMM8_Y1	26	/* Y1 流水线 8 位 */
#define R_TILEGX_DEST_IMM8_X1	27	/* X1 流水线目的 8 位 */
#define R_TILEGX_MT_IMM14_X1	28	/* X1 流水线 mtspr */
#define R_TILEGX_MF_IMM14_X1	29	/* X1 流水线 mfspr */
#define R_TILEGX_MMSTART_X0	30	/* X0 流水线 mm "start" */
#define R_TILEGX_MMEND_X0	31	/* X0 流水线 mm "end" */
#define R_TILEGX_SHAMT_X0	32	/* X0 流水线移位量 */
#define R_TILEGX_SHAMT_X1	33	/* X1 流水线移位量 */
#define R_TILEGX_SHAMT_Y0	34	/* Y0 流水线移位量 */
#define R_TILEGX_SHAMT_Y1	35	/* Y1 流水线移位量 */
#define R_TILEGX_IMM16_X0_HW0	36	/* X0 流水线 hword 0 */
#define R_TILEGX_IMM16_X1_HW0	37	/* X1 流水线 hword 0 */
#define R_TILEGX_IMM16_X0_HW1	38	/* X0 流水线 hword 1 */
#define R_TILEGX_IMM16_X1_HW1	39	/* X1 流水线 hword 1 */
#define R_TILEGX_IMM16_X0_HW2	40	/* X0 流水线 hword 2 */
#define R_TILEGX_IMM16_X1_HW2	41	/* X1 流水线 hword 2 */
#define R_TILEGX_IMM16_X0_HW3	42	/* X0 流水线 hword 3 */
#define R_TILEGX_IMM16_X1_HW3	43	/* X1 流水线 hword 3 */
#define R_TILEGX_IMM16_X0_HW0_LAST 44	/* X0 流水线最后 hword 0 */
#define R_TILEGX_IMM16_X1_HW0_LAST 45	/* X1 流水线最后 hword 0 */
#define R_TILEGX_IMM16_X0_HW1_LAST 46	/* X0 流水线最后 hword 1 */
#define R_TILEGX_IMM16_X1_HW1_LAST 47	/* X1 流水线最后 hword 1 */
#define R_TILEGX_IMM16_X0_HW2_LAST 48	/* X0 流水线最后 hword 2 */
#define R_TILEGX_IMM16_X1_HW2_LAST 49	/* X1 流水线最后 hword 2 */
#define R_TILEGX_IMM16_X0_HW0_PCREL 50	/* X0 流水线 PC 相对 hword 0 */
#define R_TILEGX_IMM16_X1_HW0_PCREL 51	/* X1 流水线 PC 相对 hword 0 */
#define R_TILEGX_IMM16_X0_HW1_PCREL 52	/* X0 流水线 PC 相对 hword 1 */
#define R_TILEGX_IMM16_X1_HW1_PCREL 53	/* X1 流水线 PC 相对 hword 1 */
#define R_TILEGX_IMM16_X0_HW2_PCREL 54	/* X0 流水线 PC 相对 hword 2 */
#define R_TILEGX_IMM16_X1_HW2_PCREL 55	/* X1 流水线 PC 相对 hword 2 */
#define R_TILEGX_IMM16_X0_HW3_PCREL 56	/* X0 流水线 PC 相对 hword 3 */
#define R_TILEGX_IMM16_X1_HW3_PCREL 57	/* X1 流水线 PC 相对 hword 3 */
#define R_TILEGX_IMM16_X0_HW0_LAST_PCREL 58 /* X0 流水线 PC 相对最后 hword 0 */
#define R_TILEGX_IMM16_X1_HW0_LAST_PCREL 59 /* X1 流水线 PC 相对最后 hword 0 */
#define R_TILEGX_IMM16_X0_HW1_LAST_PCREL 60 /* X0 流水线 PC 相对最后 hword 1 */
#define R_TILEGX_IMM16_X1_HW1_LAST_PCREL 61 /* X1 流水线 PC 相对最后 hword 1 */
#define R_TILEGX_IMM16_X0_HW2_LAST_PCREL 62 /* X0 流水线 PC 相对最后 hword 2 */
#define R_TILEGX_IMM16_X1_HW2_LAST_PCREL 63 /* X1 流水线 PC 相对最后 hword 2 */
#define R_TILEGX_IMM16_X0_HW0_GOT 64	/* X0 流水线 hword 0 GOT 偏移 */
#define R_TILEGX_IMM16_X1_HW0_GOT 65	/* X1 流水线 hword 0 GOT 偏移 */
#define R_TILEGX_IMM16_X0_HW0_PLT_PCREL 66 /* X0 流水线 PC 相对 PLT hword 0 */
#define R_TILEGX_IMM16_X1_HW0_PLT_PCREL 67 /* X1 流水线 PC 相对 PLT hword 0 */
#define R_TILEGX_IMM16_X0_HW1_PLT_PCREL 68 /* X0 流水线 PC 相对 PLT hword 1 */
#define R_TILEGX_IMM16_X1_HW1_PLT_PCREL 69 /* X1 流水线 PC 相对 PLT hword 1 */
#define R_TILEGX_IMM16_X0_HW2_PLT_PCREL 70 /* X0 流水线 PC 相对 PLT hword 2 */
#define R_TILEGX_IMM16_X1_HW2_PLT_PCREL 71 /* X1 流水线 PC 相对 PLT hword 2 */
#define R_TILEGX_IMM16_X0_HW0_LAST_GOT 72 /* X0 流水线最后 hword 0 GOT 偏移 */
#define R_TILEGX_IMM16_X1_HW0_LAST_GOT 73 /* X1 流水线最后 hword 0 GOT 偏移 */
#define R_TILEGX_IMM16_X0_HW1_LAST_GOT 74 /* X0 流水线最后 hword 1 GOT 偏移 */
#define R_TILEGX_IMM16_X1_HW1_LAST_GOT 75 /* X1 流水线最后 hword 1 GOT 偏移 */
#define R_TILEGX_IMM16_X0_HW3_PLT_PCREL 76 /* X0 流水线 PC 相对 PLT hword 3 */
#define R_TILEGX_IMM16_X1_HW3_PLT_PCREL 77 /* X1 流水线 PC 相对 PLT hword 3 */
#define R_TILEGX_IMM16_X0_HW0_TLS_GD 78	/* X0 流水线 hword 0 TLS GD 偏移 */
#define R_TILEGX_IMM16_X1_HW0_TLS_GD 79	/* X1 流水线 hword 0 TLS GD 偏移 */
#define R_TILEGX_IMM16_X0_HW0_TLS_LE 80	/* X0 流水线 hword 0 TLS LE 偏移 */
#define R_TILEGX_IMM16_X1_HW0_TLS_LE 81	/* X1 流水线 hword 0 TLS LE 偏移 */
#define R_TILEGX_IMM16_X0_HW0_LAST_TLS_LE 82 /* X0 流水线最后 hword 0 LE 偏移 */
#define R_TILEGX_IMM16_X1_HW0_LAST_TLS_LE 83 /* X1 流水线最后 hword 0 LE 偏移 */
#define R_TILEGX_IMM16_X0_HW1_LAST_TLS_LE 84 /* X0 流水线最后 hword 1 LE 偏移 */
#define R_TILEGX_IMM16_X1_HW1_LAST_TLS_LE 85 /* X1 流水线最后 hword 1 LE 偏移 */
#define R_TILEGX_IMM16_X0_HW0_LAST_TLS_GD 86 /* X0 流水线最后 hword 0 GD 偏移 */
#define R_TILEGX_IMM16_X1_HW0_LAST_TLS_GD 87 /* X1 流水线最后 hword 0 GD 偏移 */
#define R_TILEGX_IMM16_X0_HW1_LAST_TLS_GD 88 /* X0 流水线最后 hword 1 GD 偏移 */
#define R_TILEGX_IMM16_X1_HW1_LAST_TLS_GD 89 /* X1 流水线最后 hword 1 GD 偏移 */
/* 重定位 90-91 目前未定义。  */
#define R_TILEGX_IMM16_X0_HW0_TLS_IE 92	/* X0 流水线 hword 0 TLS IE 偏移 */
#define R_TILEGX_IMM16_X1_HW0_TLS_IE 93	/* X1 流水线 hword 0 TLS IE 偏移 */
#define R_TILEGX_IMM16_X0_HW0_LAST_PLT_PCREL 94 /* X0 流水线 PC 相对 PLT 最后 hword 0 */
#define R_TILEGX_IMM16_X1_HW0_LAST_PLT_PCREL 95 /* X1 流水线 PC 相对 PLT 最后 hword 0 */
#define R_TILEGX_IMM16_X0_HW1_LAST_PLT_PCREL 96 /* X0 流水线 PC 相对 PLT 最后 hword 1 */
#define R_TILEGX_IMM16_X1_HW1_LAST_PLT_PCREL 97 /* X1 流水线 PC 相对 PLT 最后 hword 1 */
#define R_TILEGX_IMM16_X0_HW2_LAST_PLT_PCREL 98 /* X0 流水线 PC 相对 PLT 最后 hword 2 */
#define R_TILEGX_IMM16_X1_HW2_LAST_PLT_PCREL 99 /* X1 流水线 PC 相对 PLT 最后 hword 2 */
#define R_TILEGX_IMM16_X0_HW0_LAST_TLS_IE 100 /* X0 流水线最后 hword 0 IE 偏移 */
#define R_TILEGX_IMM16_X1_HW0_LAST_TLS_IE 101 /* X1 流水线最后 hword 0 IE 偏移 */
#define R_TILEGX_IMM16_X0_HW1_LAST_TLS_IE 102 /* X0 流水线最后 hword 1 IE 偏移 */
#define R_TILEGX_IMM16_X1_HW1_LAST_TLS_IE 103 /* X1 流水线最后 hword 1 IE 偏移 */
/* 重定位 104-105 目前未定义。  */
#define R_TILEGX_TLS_DTPMOD64	106	/* 符号所属模块的 64 位 ID */
#define R_TILEGX_TLS_DTPOFF64	107	/* TLS 块中的 64 位偏移 */
#define R_TILEGX_TLS_TPOFF64	108	/* 静态 TLS 块中的 64 位偏移 */
#define R_TILEGX_TLS_DTPMOD32	109	/* 符号所属模块的 32 位 ID */
#define R_TILEGX_TLS_DTPOFF32	110	/* TLS 块中的 32 位偏移 */
#define R_TILEGX_TLS_TPOFF32	111	/* 静态 TLS 块中的 32 位偏移 */
#define R_TILEGX_TLS_GD_CALL	112	/* TLS GD 的 "jal" */
#define R_TILEGX_IMM8_X0_TLS_GD_ADD 113	/* X0 流水线 TLS GD 的 "addi" */
#define R_TILEGX_IMM8_X1_TLS_GD_ADD 114	/* X1 流水线 TLS GD 的 "addi" */
#define R_TILEGX_IMM8_Y0_TLS_GD_ADD 115	/* Y0 流水线 TLS GD 的 "addi" */
#define R_TILEGX_IMM8_Y1_TLS_GD_ADD 116	/* Y1 流水线 TLS GD 的 "addi" */
#define R_TILEGX_TLS_IE_LOAD	117	/* TLS IE 的 "ld_tls" */
#define R_TILEGX_IMM8_X0_TLS_ADD 118	/* X0 流水线 TLS GD/IE 的 "addi" */
#define R_TILEGX_IMM8_X1_TLS_ADD 119	/* X1 流水线 TLS GD/IE 的 "addi" */
#define R_TILEGX_IMM8_Y0_TLS_ADD 120	/* Y0 流水线 TLS GD/IE 的 "addi" */
#define R_TILEGX_IMM8_Y1_TLS_ADD 121	/* Y1 流水线 TLS GD/IE 的 "addi" */

#define R_TILEGX_GNU_VTINHERIT	128	/* GNU C++ vtable 层次结构 */
#define R_TILEGX_GNU_VTENTRY	129	/* GNU C++ vtable 成员用法 */

#define R_TILEGX_NUM		130


#endif	/* elf.h */
