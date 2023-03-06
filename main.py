import sys
from aiohttp import ClientSession
from asyncio import run
from functools import reduce
from pprint import pprint
from re import match
from typing import Any, List, Mapping, Tuple, Union
from pydantic import BaseModel


class UnknownTypes(BaseModel):
    pass


class LeafTypes(BaseModel):
    t: type


class OrTypes(BaseModel):
    t: List["Types"]


class ArrayTypes(BaseModel):
    t: "Types"


class ObjectTypes(BaseModel):
    t: Mapping[str, "Types"]


class Types(BaseModel):
    t: Union[LeafTypes, ArrayTypes, ObjectTypes, OrTypes, UnknownTypes]


ArrayTypes.update_forward_refs()
ObjectTypes.update_forward_refs()
OrTypes.update_forward_refs()


def __is_single_type(acc: Tuple[bool, Types], cur_typ: Types) -> Tuple[bool, Types]:
    is_single, prev_typ = acc
    if not is_single:
        return is_single, prev_typ
    else:
        return prev_typ == cur_typ, cur_typ


def __distribute_types(typ_list: List[Types]) -> Tuple[List[ObjectTypes], List[Union[LeafTypes, ArrayTypes]]]:
    def distinct(lst: List) -> List:
        flag = len(lst) > 1
        unique_lst = []
        for x in lst:
            if flag and isinstance(x, UnknownTypes):
                continue
            if x not in unique_lst:
                unique_lst.append(x)
        return unique_lst
    if len(typ_list) == 0:
        return [], []
    obj_typ_list = [
        typ.t for typ in typ_list if isinstance(typ.t, ObjectTypes)]
    remain_typ_list = [typ.t for typ in typ_list if not isinstance(
        typ.t, ObjectTypes) and not isinstance(typ.t, OrTypes)]
    or_typ_list = [typ.t for typ in typ_list if isinstance(typ.t, OrTypes)]
    (obj_typ_list_from_or, remain_typ_list_from_or) = __distribute_types(
        [typ for or_typ in or_typ_list for typ in or_typ.t])
    obj_typ_list.extend(obj_typ_list_from_or)
    remain_typ_list.extend(remain_typ_list_from_or)
    return obj_typ_list, distinct(remain_typ_list)


def __merge_various_types(typ_list: List[Types]) -> Types:
    obj_typ_list, remain_typ_list = __distribute_types(typ_list)
    if len(obj_typ_list) == 0 and len(remain_typ_list) == 0:
        return Types(t=UnknownTypes())
    elif len(obj_typ_list) == 0:
        remain_typ = [Types(t=typ) for typ in remain_typ_list]
        if len(remain_typ) == 1:
            return remain_typ[0]
        else:
            return Types(t=OrTypes(t=remain_typ))
    elif len(obj_typ_list) > 0 and len(remain_typ_list) == 0:
        obj_typ = __merge_obj_types(obj_typ_list)
        return Types(t=obj_typ)
    else:
        obj_typ = __merge_obj_types(obj_typ_list)
        remain_typ = [Types(t=typ) for typ in remain_typ_list]
        remain_typ.append(Types(t=obj_typ))
        return Types(t=OrTypes(t=remain_typ))


def __merge_obj_types(obj_typ_list: List[ObjectTypes]) -> ObjectTypes:
    assert len(obj_typ_list) > 0
    keys = set()
    for obj_typ in obj_typ_list:
        keys.update(obj_typ.t.keys())
    obj = dict()
    for key in sorted(keys):
        typ_list = [obj_typ.t[key] if key in obj_typ.t else Types(t=UnknownTypes())
                    for obj_typ in obj_typ_list]
        obj[key] = __merge_various_types(typ_list)
    return ObjectTypes(t=obj)


def __extract_array(json: List[Any]) -> ArrayTypes:
    if len(json) == 0:
        return ArrayTypes(t=Types(t=UnknownTypes()))
    arr = [extract(item) for item in json]
    typ_list = [typ.t for typ in arr]
    (is_single_type, _) = reduce(__is_single_type, arr, (True, arr[0]))
    if is_single_type:
        return ArrayTypes(t=arr[0])
    elif all([isinstance(typ, ObjectTypes) for typ in typ_list]):
        obj_typ = __merge_obj_types(typ_list)  # type: ignore
        return ArrayTypes(t=Types(t=obj_typ))
    else:
        return ArrayTypes(t=__merge_various_types(arr))


def __extract_object(json: Mapping[str, Any]) -> ObjectTypes:
    obj = dict()
    for key, value in json.items():
        obj[key] = extract(value)
    return ObjectTypes(t=obj)


def extract(json: Any) -> Types:
    if isinstance(json, List):
        arr_types = __extract_array(json)
        return Types(t=arr_types)
    elif isinstance(json, Mapping):
        obj_types = __extract_object(json)
        return Types(t=obj_types)
    else:
        leaf_types = LeafTypes(t=type(json))
        return Types(t=leaf_types)


def to_json(typ: Types) -> str | Tuple[Any] | List[Any] | Mapping[str, Any]:
    if isinstance(typ.t, UnknownTypes):
        return "Unknown"
    elif isinstance(typ.t, LeafTypes):
        res = match(r"<class '(\w+)'>", str(typ.t.t))
        if res:
            return res.groups()[0]
        else:
            return str(typ.t.t)
    elif isinstance(typ.t, OrTypes):
        return tuple([to_json(typ) for typ in typ.t.t])
    elif isinstance(typ.t, ArrayTypes):
        return [to_json(typ.t.t)]
    elif isinstance(typ.t, ObjectTypes):
        return dict([(key, to_json(value)) for key, value in typ.t.t.items()])
    else:
        raise Exception("Invalid Type")


async def main():
    url = sys.argv[1]
    print(f"> URL: {url}")
    async with ClientSession() as session:
        response = await session.get(url=url)
        print(f"> Reponse: {response.ok}")
        json = await response.json()
        print("> Json")
        await session.close()
    raw_schema = extract(json)
    print("> Extract")
    refine_schema = to_json(raw_schema)
    print("> Refine")
    pprint(refine_schema)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run(main())
    else:
        json = """
        {
    "name": "Ethereum Mainnet",
    "chain": "ETH",
    "icon": "ethereum",
    "rpc": [
      "https://mainnet.infura.io/v3/${INFURA_API_KEY}",
      "wss://mainnet.infura.io/ws/v3/${INFURA_API_KEY}",
      "https://api.mycryptoapi.com/eth",
      "https://cloudflare-eth.com"
    ],
    "features": [
      {
        "name": "EIP155"
      },
      {
        "name": "EIP1559"
      }
    ],
    "faucets": [],
    "nativeCurrency": {
      "name": "Ether",
      "symbol": "ETH",
      "decimals": 18
    },
    "infoURL": "https://ethereum.org",
    "shortName": "eth",
    "chainId": 1,
    "networkId": 1,
    "slip44": 60,
    "ens": {
      "registry": "0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e"
    },
    "explorers": [
      {
        "name": "etherscan",
        "url": "https://etherscan.io",
        "standard": "EIP3091"
      }
    ]
  }
        """
        from json import loads
        raw_schema = extract(loads(json))
        print("Extract")
        refine_schema = to_json(raw_schema)
        print("Refine")
        pprint(refine_schema)
