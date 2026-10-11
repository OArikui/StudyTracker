from datetime import datetime, timedelta, timezone
from study_tracker.analysis import Record, aggregate_duration, overlap_seconds

JST = timezone(timedelta(hours=9))

def rec(subject, start_h, duration):
    start = datetime(2026,10,5,start_h,0,tzinfo=JST)
    end = start + timedelta(minutes=duration)
    return Record(1,1,start,end,True,"2026.10.05","通常",subject,"教材","位置","p","1-2",(),())

def test_overlap_and_aggregate():
    rows=[rec("物理",10,30),rec("物理",11,30),rec("数学",12,60)]
    start=datetime(2026,10,5,10,15,tzinfo=JST)
    end=datetime(2026,10,5,12,30,tzinfo=JST)
    assert overlap_seconds(rows[0],start,end)==900
    data=dict(aggregate_duration(rows,key=lambda r:r.subject,start=start,end=end))
    assert data["物理"]==2700
    assert data["数学"]==1800
