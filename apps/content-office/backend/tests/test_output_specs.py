from office.output_specs import output_issues

def test_blog_contract_and_legacy():
    assert output_issues({'body':'old'}) == []
    good={'body':'가'*1500,'titles':['가','나','다'],'hashtags':['#가','#나','#다','#라','#마']}
    assert output_issues(good)==[]
    assert output_issues({**good,'body':'짧음'})
    assert output_issues({**good,'hashtags':['#가']*5})
