#include "native_direct_pose.hpp"
#include <cassert>

int main() {
    using namespace BotwCraftDirect;
    Target data{};
    data.sequence=2;
    data.magic=kMagic;
    data.version=kVersion;
    data.flags=kActive|kFirstPerson|kFly;
    data.timeMs=1234;
    data.minecraftFrame=19;
    data.position[0]=-1125;
    data.position[1]=240;
    data.position[2]=1906;
    data.eye[0]=-1125;
    data.eye[1]=241.62f;
    data.eye[2]=1906;
    data.forward[0]=0.f; data.forward[1]=0.f; data.forward[2]=1.f;
    assert(Accept(data,2,2,1250));
    assert(!Accept(data,3,3,1250)); // writer in progress
    assert(!Accept(data,2,4,1250)); // torn read
    assert(!Accept(data,2,2,2250)); // stale producer
    data.flags=0;
    assert(!Accept(data,2,2,1250)); // disconnected
    data.flags=kActive|kFirstPerson;
    data.forward[2]=0;
    assert(!Accept(data,2,2,1250)); // broken camera
    data.forward[2]=1;
    data.position[0]=__builtin_nanf("");
    assert(!Accept(data,2,2,1250)); // NaN guard
    return 0;
}
