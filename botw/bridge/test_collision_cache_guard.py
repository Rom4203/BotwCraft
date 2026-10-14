import tempfile
import unittest
import struct
from pathlib import Path
from collision_cache_guard import ensure_cache,valid_tile

class CollisionCacheTests(unittest.TestCase):
    def test_restores_previous_valid_terrain_and_decor(self):
        with tempfile.TemporaryDirectory() as temp:
            parent=Path(temp)
            former=parent/'BotwCraft-V1'/'terrain_cache'
            terrain=former/'terrain'; terrain.mkdir(parents=True)
            decor=former/'decor';decor.mkdir(parents=True)
            tile=b'BTRI'+struct.pack('<IiiIii',1,20,16,0,0,0)+bytes(24)
            (terrain/'20-16.btri').write_bytes(tile)
            (decor/'20-16.btri').write_bytes(tile)
            new=parent/'BotwCraft-V2';new.mkdir()
            count,_=ensure_cache(new,parent)
            self.assertEqual(count,1)
            self.assertEqual((new/'terrain_cache'/'terrain'/'20-16.btri').read_bytes(),tile)
            self.assertEqual((new/'terrain_cache'/'decor'/'20-16.btri').read_bytes(),tile)
            self.assertEqual(ensure_cache(new,parent)[0],1)
    def test_malformed_cache_does_not_allow_silent_gameplay(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            folder=root/'terrain_cache'/'terrain';folder.mkdir(parents=True)
            fake=folder/'20-16.btri'
            fake.write_bytes(b'BTRI'+bytes(48))
            self.assertFalse(valid_tile(fake))
            self.assertEqual(ensure_cache(root,root.parent)[0],0)

if __name__=='__main__':
    unittest.main()
