# CDNSP
Python3 script to connect to Nintendo CDN and print title info, download titles, and create NSP files

Configure `CDNSPconfig.json` before use.<br> 
For Windows paths, be sure to use double backspaces: `C:\\Users\\Desktop\\...`<br>
Currently includes hactool binaries for macOS and Windows.<br>
Supply your own `keys.txt` file filled with Switch keys.

```
usage: CDNSP.py [-h] [-i TID [TID ...]] [-g TID-VER-TKEY [TID-VER-TKEY ...]]
                [-s VER [VER ...]] [-r]

optional arguments:
  -h, --help                          show this help message and exit
  -i TID [TID ...]                    print info about a title:
                                         - name from shogun
                                         - available updates from versionlist
  -g TID-VER-TKEY [TID-VER-TKEY ...]  download games/updates/DLC's:
                                         - titlekey argument is optional
                                         - format TitleID-Version(-Titlekey)
                                         - update TitleID's are the same as the base game's,
                                           with the three last digits replaced with '800'
                                         - version is 0 for base games, multiple of 65536 (0x10000) for updates
  -s VER [VER ...]                    download system updates:
                                         - version is computed as follows (credit goes to SocraticBliss):
                                         - X.Y.Z-B (all decimal integers)
                                           => VER = X*67108864 + Y*1048576 + Z*65536 + B
                                                 (= X*0x4000000 + Y*0x100000 + Z*0x10000 + B)
                                         - 0 will download the lastest update
  -r                                  repack the downloaded games to nsp format
                                         - for non-update titles, titlekey is required to generate tik
                                         - will generate/download cert, tik and cnmt.xml
```

## Requirements:
  * requests
  * tqdm
  * pyopenssl
  
 ## Features:
   * Obtain and display base game info when downloading a game, update or DLC (name, size, available updates)
   * Iterate through multiple regions (starting with prefered region in config file) to find title info
   * Name NSP file with the format: Title Name \[TYPE]\[TITLE ID] where type is either GAME, UPDATE or DLC. Name is restricted to 64 characters, including extension.
   * Strips tItle names of special characters
