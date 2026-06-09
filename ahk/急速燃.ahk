#NoEnv
#NoTrayIcon
#SingleInstance
SetKeyDelay, -1
SendMode Input
global lastKeyTime := 0,lastKeyTime1 := 0, lastKeyTime2 := 0, lastKeyTime3 := 0, lastKeyTime4 := 0, lastKeyTime5 := 0, lastKeyTime6 := 0, lastKeyTime7 := 0
Gui +OwnDialogs
GuiControlGet, kai, , startfont
ScriptDir := A_ScriptDir
NewFolder := ScriptDir . "\config"
FileCreateDir, %NewFolder%
IniFilePath := ScriptDir . "\config\成小林症状急速燃.ini"

IniWrite, "free", %iniFilePath%, "本脚本免费使用", by:
    wpcolor:="wpcolor"
    keys := ["wp1","wp2", "wp3","wp4", "wp5"]
    for index, key in keys {
        IniRead, %key%x, %iniFilePath%, %wpcolor%, %key%x
        IniRead, %key%y, %iniFilePath%, %wpcolor%, %key%y
        IniRead, %key%color, %iniFilePath%, %wpcolor%, %key%color
    }
    twpcolor:="twpcolor"
    keys := ["twp2","twp3","twp4","twp5"]
    for index, key in keys {
        IniRead, %key%x, %iniFilePath%, %twpcolor%, %key%x
        IniRead, %key%y, %iniFilePath%, %twpcolor%, %key%y
        IniRead, %key%color, %iniFilePath%, %twpcolor%, %key%color
    }
    tycolor:="tycolor"
    keys := ["ty1", "ty2", "ty3", "ty4", "ty5"]
    for index, key in keys {
        IniRead, %key%x, %iniFilePath%, %tycolor%, %key%x
        IniRead, %key%y, %iniFilePath%, %tycolor%, %key%y
        IniRead, %key%color, %iniFilePath%, %tycolor%, %key%color
    }
    fcolor:="fcolor"
    keys := ["f1", "f2", "f3", "f4", "f5","point0","point","point1","point2","point3","point4","point5","pointA","pointB"]
    for index, key in keys {
        IniRead, %key%x, %iniFilePath%, %fcolor%, %key%x
        IniRead, %key%y, %iniFilePath%, %fcolor%, %key%y
        IniRead, %key%color, %iniFilePath%, %fcolor%, %key%color
    }
    Hotkeys:="Hotkeys"
    keys := ["wp1key", "wp2key", "wp3key", "wp4key", "wp5key", "ty1key", "ty2key", "ty3key", "ty4key", "ty5key", "f1key", "f2key", "f3key", "f4key", "f5key", "qwqkey", "startkey", "savecolorkey", "savekey","alltime"]
    defaultValues := ["1", "2", "3", "4", "5", "e", "x", "c", "z", "", "F1", "F2", "F3", "F4", "F5", "``", "capslock", "f9", "f10","0"]
    for index, key in keys {
        IniRead, %key%, %iniFilePath%, %Hotkeys%, %key%
        if (%key% = "" or %key% = "error") {
            %key% := defaultValues[index]
        }
    }
    qwq:="qwq"
    IniRead, qwqx, %iniFilePath%, %qwq%, qwqx
    IniRead, qwqy, %iniFilePath%, %qwq%, qwqy
    IniRead, qwqcolor, %iniFilePath%, %qwq%, qwqcolor
    IniRead, startfont, %iniFilePath%, %Hotkeys%, startfont
    if(startfont="" or startfont= "error")
    {
        startfont:= "启动中"
    }
    mieshi:="mieshi"
    IniRead, mieshix, %iniFilePath%, %mieshi%, mieshix
    IniRead, mieshiy, %iniFilePath%, %mieshi%, mieshiy
    IniRead, mieshicolor, %iniFilePath%, %mieshi%, mieshicolor
    IniRead, startfont, %iniFilePath%, %Hotkeys%, startfont
    if(startfont="" or startfont= "error")
    {
        startfont:= "启动中"
    }
    Label=%1%
    if (Label!="")
    {
        Suspend, On
        if IsLabel(Label)
            Gosub, %Label%
        ExitApp
    }
    Menu, Tray, Icon
    Class Thread
    {
        __New(Label)
        {
            if (A_IsCompiled)
                Run, "%A_ScriptFullPath%" /f "%Label%",,, pid
            else
                Run, "%A_AhkPath%" /f "%A_ScriptFullPath%" "%Label%",,, pid
            this.pid:=pid
        }
        __Delete()
        {
            Process, Close, % this.pid
        }
    }
    Hotkey, %startkey%, startrun
    Hotkey, %savecolorkey%, findcolor
    Hotkey, %savekey%, savekey
return
startrun:
    xPos := qwqx-20
    yPos := qwqy-30
    SplashImage,, X%xPos% Y%yPos% H22 W60 fs8 CW00FF00 CT000000 ZX2 ZY5 B8, %startfont%

    aaa1 := (onoff1 := !onoff1) ? new Thread("a1") : ""
    aaa2 := (onoff2 := !onoff2) ? new Thread("a2") : ""

    if(startkey =="capslock" )
    {
        if( onoff1 = 0)
        {
            SplashImage, Off
            SetCapsLockState, Off
        }
    }
    if(startkey !="capslock" )
    {
        if( onoff1 = 0)
        {
            SplashImage, Off
        }
    }
return
a1:
    Loop
    {
        getpoint0:=GetPixelColor(point0x,point0y)
        if (getpoint0==point0color)
        {
            getpoint1:=GetPixelColor(point1x,point1y)
            if (getpoint1!="0x000000")
            {
                lastKeyTime7 := A_TickCount
                loop 10
                {
                    SendLoop(wp4key,91)
                }
            }
            lastKeyTime := A_TickCount
            getpoint2:=GetPixelColor(point2x,point2y)
            if (getpoint2!="0x000000")
            {
                lastKeyTime6 := A_TickCount
                loop 10
                {
                    SendLoop(wp5key,91)
                }
            }
            getpoint:=GetPixelColor(pointx,pointy)
            if (getpoint==pointcolor)
            {
                loop 10
                {
                    SendLoop(wp2key,48)
                }
                lastKeyTime := A_TickCount
            }
            loop 10
            {
                SendLoop(f1key,12)
            }
        }
        getty5:=GetPixelColor(ty5x,ty5y)
        if (getty5==ty5color)
        {
            loop 10
            {
                SendLoop(ty5key,25)
            }
        }
        getwp5:=GetPixelColor(wp5x,wp5y)
        if (getwp5==wp5color)
        {
            getwp3:=GetPixelColor(wp3x,wp3y)
            if (getwp3==wp3color)
            {
                loop 10
                {
                    SendLoop(wp3key,34)
                }
            }
            loop 10
            {
                SendLoop(wp5key,104)
            }
        }
        getty4:=GetPixelColor(ty4x,ty4y)
        if (getty4==ty4color)
        {
            loop 10
            {
                SendLoop(ty4key,31)
            }
        }
        getwp3:=GetPixelColor(wp3x,wp3y)
        if (getwp3==wp3color)
        {
            loop 10
            {
                SendLoop(wp3key,34)
            }
        }
        getwp4:=GetPixelColor(wp4x,wp4y)
        if (getwp4==wp4color)
        {
            loop 10
            {
                SendLoop(wp4key,113)
            }
            currentWeapon := "wp2"
        }
        getwp2:=GetPixelColor(wp2x,wp2y)
        if (getwp2==wp2color)
        {
            getwp3:=GetPixelColor(wp3x,wp3y)
            if (getwp3==wp3color)
            {
                loop 10
                {
                    SendLoop(wp3key,34)
                }
            }
            loop 10
            {
                SendLoop(wp2key,104)
            }
        }
        getwp4:=GetPixelColor(wp4x,wp4y)
        if (getwp4==wp4color)
        {
            loop 10
            {
                SendLoop(wp4key,113)
            }
            currentWeapon := "wp2"
        }
        gettwp4:=GetPixelColor(twp4x,twp4y)
        if (gettwp4==twp4color && (A_TickCount - lastKeyTime1 >= 3000))
        {
            lastKeyTime1 := A_TickCount
            loop 10
            {
                SendLoop(wp4key,68)
            }
            currentWeapon := "twp2"
        }
        gettwp5:=GetPixelColor(twp5x,twp5y)
        if (gettwp5==twp5color)
        {
            getwp3:=GetPixelColor(wp3x,wp3y)
            if (getwp3==wp3color)
            {
                loop 10
                {
                    SendLoop(wp3key,34)
                }
            }
            loop 10
            {
                SendLoop(wp5key,261)
            }
            currentWeapon := "twp2"
        }
        getpoint5:=GetPixelColor(point5x,point5y)
        if (getpoint5==point5color)
        {
            loop 10
            {
                SendLoop(wp4key,68)
            }
            currentWeapon := "twp2"
        }
        getqwq:=GetPixelColor(qwqx,qwqy)
        if (getqwq==qwqcolor && currentWeapon == "wp2")
        {
            loop 10
            {
                SendLoop(qwqkey,12)
            }
            lastKeyTime1 := A_TickCount
            loop 10
            {
                SendLoop(wp4key,68)
            }
            currentWeapon := "twp2"
            getty4:=GetPixelColor(ty4x,ty4y)
            if (getty4==ty4color)
            {
                loop 10
                {
                    SendLoop(ty4key,31)
                }
            }
            getf1:=GetPixelColor(f1x,f1y)
            if (getf1==f1color || (A_TickCount - lastKeyTime >= 8000))
            {
                getty4:=GetPixelColor(ty4x,ty4y)
                if (getty4==ty4color)
                {
                    loop 10
                    {
                        SendLoop(ty4key,31)
                    }
                }
                getwp5:=GetPixelColor(wp5x,wp5y)
                if (getwp5==wp5color)
                {
                    getwp3:=GetPixelColor(wp3x,wp3y)
                    if (getwp3==wp3color)
                    {
                        loop 10
                        {
                            SendLoop(wp3key,34)
                        }
                    }
                    loop 10
                    {
                        SendLoop(wp5key,104)
                    }
                    currentWeapon := "twp"
                }
                gettwp4:=GetPixelColor(twp4x,twp4y)
                if (gettwp4==twp4color && (A_TickCount - lastKeyTime1 >= 3000))
                {
                    lastKeyTime1 := A_TickCount
                    loop 10
                    {
                        SendLoop(wp4key,68)
                    }
                    currentWeapon := "twp2"
                }
                getpoint5:=GetPixelColor(point5x,point5y)
                if (getpoint5==point5color)
                {
                    loop 10
                    {
                        SendLoop(wp4key,68)
                    }
                    currentWeapon := "twp2"
                }
                getwp3:=GetPixelColor(wp3x,wp3y)
                if (getwp3==wp3color)
                {
                    loop 10
                    {
                        SendLoop(wp3key,34)
                    }
                }
                loop 10
                {
                    SendLoop(f1key,12)
                }
                loop 10
                {
                    SendLoop(wp2key,48)
                }
                lastKeyTime := A_TickCount
                getpoint2:=GetPixelColor(point2x,point2y)
                if (getpoint2!="0x000000")
                {
                    lastKeyTime6 := A_TickCount
                    loop 10
                    {
                        SendLoop(wp5key,91)
                    }
                }
                getpoint1:=GetPixelColor(point1x,point1y)
                if (getpoint1!="0x000000")
                {
                    lastKeyTime7 := A_TickCount
                    loop 10
                    {
                        SendLoop(wp4key,91)
                    }
                }
                loop 10
                {
                    SendLoop(f1key,12)
                }
                getwp3:=GetPixelColor(wp3x,wp3y)
                if (getwp3!="0x000000")
                {
                    loop 10
                    {
                        SendLoop(wp3key,34)
                    }
                }
                getwp2:=GetPixelColor(wp2x,wp2y)
                if (getwp2!="0x000000")
                {
                    getwp3:=GetPixelColor(wp3x,wp3y)
                    if (getwp3!="0x000000")
                    {
                        loop 10
                        {
                            SendLoop(wp3key,34)
                        }
                    }
                    loop 10
                    {
                        SendLoop(wp2key,104)
                    }
                }
            }
        }
        getqwq:=GetPixelColor(qwqx,qwqy)
        if (getqwq==qwqcolor && currentWeapon == "twp2")
        {
            loop 10
            {
                SendLoop(qwqkey,12)
            }
            loop 10
            {
                SendLoop(wp4key,113)
            }
            currentWeapon := "wp2"
            getty4:=GetPixelColor(ty4x,ty4y)
            if (getty4==ty4color)
            {
                loop 10
                {
                    SendLoop(ty4key,31)
                }
            }
            getf1:=GetPixelColor(f1x,f1y)
            if (getf1==f1color || (A_TickCount - lastKeyTime >= 8000))
            {
                getty4:=GetPixelColor(ty4x,ty4y)
                if (getty4==ty4color)
                {
                    loop 10
                    {
                        SendLoop(ty4key,31)
                    }
                }
                getwp5:=GetPixelColor(wp5x,wp5y)
                if (getwp5==wp5color)
                {
                    getwp3:=GetPixelColor(wp3x,wp3y)
                    if (getwp3==wp3color)
                    {
                        loop 10
                        {
                            SendLoop(wp3key,34)
                        }
                    }
                    loop 10
                    {
                        SendLoop(wp5key,104)
                    }
                    currentWeapon := "twp"
                }
                gettwp4:=GetPixelColor(twp4x,twp4y)
                if (gettwp4==twp4color && (A_TickCount - lastKeyTime1 >= 3000))
                {
                    lastKeyTime1 := A_TickCount
                    loop 10
                    {
                        SendLoop(wp4key,68)
                    }
                    currentWeapon := "twp2"
                }
                getpoint5:=GetPixelColor(point5x,point5y)
                if (getpoint5==point5color)
                {
                    loop 10
                    {
                        SendLoop(wp4key,68)
                    }
                    currentWeapon := "twp2"
                }
                getwp3:=GetPixelColor(wp3x,wp3y)
                if (getwp3==wp3color)
                {
                    loop 10
                    {
                        SendLoop(wp3key,34)
                    }
                }
                loop 10
                {
                    SendLoop(f1key,12)
                }
                loop 10
                {
                    SendLoop(wp2key,48)
                }
                lastKeyTime := A_TickCount
                getpoint2:=GetPixelColor(point2x,point2y)
                if (getpoint2!="0x000000")
                {
                    lastKeyTime6 := A_TickCount
                    loop 10
                    {
                        SendLoop(wp5key,91)
                    }
                }
                getpoint1:=GetPixelColor(point1x,point1y)
                if (getpoint1!="0x000000")
                {
                    lastKeyTime7 := A_TickCount
                    loop 10
                    {
                        SendLoop(wp4key,91)
                    }
                }
                loop 10
                {
                    SendLoop(f1key,12)
                }
                getwp3:=GetPixelColor(wp3x,wp3y)
                if (getwp3!="0x000000")
                {
                    loop 10
                    {
                        SendLoop(wp3key,34)
                    }
                }
                getwp2:=GetPixelColor(wp2x,wp2y)
                if (getwp2!="0x000000")
                {
                    getwp3:=GetPixelColor(wp3x,wp3y)
                    if (getwp3!="0x000000")
                    {
                        loop 10
                        {
                            SendLoop(wp3key,34)
                        }
                    }
                    loop 10
                    {
                        SendLoop(wp2key,104)
                    }
                }
            }
        }
        getf1:=GetPixelColor(f1x,f1y)
        if (getf1==f1color || (A_TickCount - lastKeyTime >= 8000))
        {
            getty4:=GetPixelColor(ty4x,ty4y)
            if (getty4==ty4color)
            {
                loop 10
                {
                    SendLoop(ty4key,31)
                }
            }
            getwp5:=GetPixelColor(wp5x,wp5y)
            if (getwp5==wp5color)
            {
                getwp3:=GetPixelColor(wp3x,wp3y)
                if (getwp3==wp3color)
                {
                    loop 10
                    {
                        SendLoop(wp3key,34)
                    }
                }
                loop 10
                {
                    SendLoop(wp5key,104)
                }
                currentWeapon := "twp"
            }
            gettwp4:=GetPixelColor(twp4x,twp4y)
            if (gettwp4==twp4color && (A_TickCount - lastKeyTime1 >= 3000))
            {
                lastKeyTime1 := A_TickCount
                loop 10
                {
                    SendLoop(wp4key,68)
                }
                currentWeapon := "twp2"
            }
            getpoint5:=GetPixelColor(point5x,point5y)
            if (getpoint5==point5color)
            {
                loop 10
                {
                    SendLoop(wp4key,68)
                }
                currentWeapon := "twp2"
            }
            getwp3:=GetPixelColor(wp3x,wp3y)
            if (getwp3==wp3color)
            {
                loop 10
                {
                    SendLoop(wp3key,34)
                }
            }
            loop 10
            {
                SendLoop(f1key,12)
            }
            loop 10
            {
                SendLoop(wp2key,48)
            }
            lastKeyTime := A_TickCount
            getpoint2:=GetPixelColor(point2x,point2y)
            if (getpoint2!="0x000000")
            {
                lastKeyTime6 := A_TickCount
                loop 10
                {
                    SendLoop(wp5key,91)
                }
            }
            getpoint1:=GetPixelColor(point1x,point1y)
            if (getpoint1!="0x000000")
            {
                lastKeyTime7 := A_TickCount
                loop 10
                {
                    SendLoop(wp4key,91)
                }
            }
            loop 10
            {
                SendLoop(f1key,12)
            }
            getwp3:=GetPixelColor(wp3x,wp3y)
            if (getwp3!="0x000000")
            {
                loop 10
                {
                    SendLoop(wp3key,34)
                }
            }
            getwp2:=GetPixelColor(wp2x,wp2y)
            if (getwp2!="0x000000")
            {
                getwp3:=GetPixelColor(wp3x,wp3y)
                if (getwp3!="0x000000")
                {
                    loop 10
                    {
                        SendLoop(wp3key,34)
                    }
                }
                loop 10
                {
                    SendLoop(wp2key,104)
                }
            }
        }
        if ((A_TickCount - lastKeyTime6 >= 17000))
        {
            getwp3:=GetPixelColor(wp3x,wp3y)
            if (getwp3==wp3color)
            {
                loop 10
                {
                    SendLoop(wp3key,34)
                }
            }
            loop 10
            {
                SendLoop(f1key,12)
            }
            loop 10
            {
                SendLoop(wp5key,91)
            }
            lastKeyTime6 := A_TickCount
            getpoint1:=GetPixelColor(point1x,point1y)
            if (getpoint1!="0x000000")
            {
                loop 10
                {
                    SendLoop(wp4key,91)
                }
            }
            getpoint:=GetPixelColor(pointx,pointy)
            if (getpoint==pointcolor)
            {
                loop 10
                {
                    SendLoop(wp2key,48)
                }
                lastKeyTime := A_TickCount
            }
            loop 10
            {
                SendLoop(f1key,12)
            }
            getwp3:=GetPixelColor(wp3x,wp3y)
            if (getwp3!="0x000000")
            {
                loop 10
                {
                    SendLoop(wp3key,34)
                }
            }
            getwp2:=GetPixelColor(wp2x,wp2y)
            if (getwp2!="0x000000")
            {
                getwp3:=GetPixelColor(wp3x,wp3y)
                if (getwp3!="0x000000")
                {
                    loop 10
                    {
                        SendLoop(wp3key,34)
                    }
                }
                loop 10
                {
                    SendLoop(wp2key,104)
                }
            }
        }
        if ((A_TickCount - lastKeyTime7 >= 13000))
        {
            getwp3:=GetPixelColor(wp3x,wp3y)
            if (getwp3==wp3color)
            {
                loop 10
                {
                    SendLoop(wp3key,34)
                }
            }
            loop 10
            {
                SendLoop(f1key,12)
            }
            loop 10
            {
                SendLoop(wp4key,91)
            }
            lastKeyTime7 := A_TickCount
            getpoint:=GetPixelColor(pointx,pointy)
            if (getpoint==pointcolor)
            {
                loop 10
                {
                    SendLoop(wp2key,48)
                }
                lastKeyTime := A_TickCount
            }
            loop 10
            {
                SendLoop(f1key,12)
            }
            getwp3:=GetPixelColor(wp3x,wp3y)
            if (getwp3!="0x000000")
            {
                loop 10
                {
                    SendLoop(wp3key,34)
                }
            }
            getwp2:=GetPixelColor(wp2x,wp2y)
            if (getwp2!="0x000000")
            {
                getwp3:=GetPixelColor(wp3x,wp3y)
                if (getwp3!="0x000000")
                {
                    loop 10
                    {
                        SendLoop(wp3key,34)
                    }
                }
                loop 10
                {
                    SendLoop(wp2key,104)
                }
            }
        }
    }
return
a2:
    loop
    {
        getty2:=GetPixelColor(ty2x,ty2y)
        if (getty2!="0x000000" && (A_TickCount - lastKeyTime2 >= 1000))
        {
            SendLoop(ty2key,0)
            SendLoop(ty3key,0)
            lastKeyTime2 := A_TickCount
        }
        getty3:=GetPixelColor(ty3x,ty3y)
        if (getty3!="0x000000" && (A_TickCount - lastKeyTime3 >= 1000))
        {
            SendLoop(ty2key,0)
            SendLoop(ty3key,0)
            lastKeyTime3 := A_TickCount
        }
        getpoint3:=GetPixelColor(point3x,point3y)
        if (getpoint3==point3color && (A_TickCount - lastKeyTime4 >= 1000))
        {
            SendLoop(ty1key,0)
            lastKeyTime4 := A_TickCount
        }
        getpoint4:=GetPixelColor(point4x,point4y)
        if (getpoint4==point4color && (A_TickCount - lastKeyTime5 >= 1000))
        {
            SendLoop(ty1key,0)
            lastKeyTime5 := A_TickCount
        }
    }
return
findcolor:
    sltime:=100
    jumptime:=100
    msgbox "下面将开始对武器技能取色"`n"请按照文字提示依次移动到技能左上角11点方向，按下" %savecolorkey%
    saveType := "wpcolor"
    wp := ["2", "3", "4", "5"]
    Loop, % wp.MaxIndex()
    {
        skill := wp[A_Index]
        Loop
        {
            tooltip "请移动到手枪/手枪技能" %skill% "，11点方向按下"%savecolorkey%
            if GetKeyState(savecolorkey, "P")
            {
                MouseGetPos, xpos, ypos
                mousemove, xpos, ypos - 200
                sleep %sltime%
                PixelGetColor, color, %xpos%, %ypos%, RGB
                IniWrite, %xpos%, %iniFilePath%, %saveType%, wp%skill%x
                IniWrite, %ypos%, %iniFilePath%, %saveType%, wp%skill%y
                IniWrite, %color%, %iniFilePath%, %saveType%, wp%skill%color
                mousemove, xpos, ypos
                tooltip "手枪/手枪技能" %skill% "获取完毕"
                sleep jumptime
                tooltip
                break
            }
            if GetKeyState("ESC", "P")
            {
                tooltip "跳过"
                sleep jumptime
                tooltip
                break
            }
        }
    }
    keys := ["wp1","wp2", "wp3","wp4", "wp5"]
    for index, key in keys {
        IniRead, %key%x, %iniFilePath%, wpcolor, %key%x
        IniRead, %key%y, %iniFilePath%, wpcolor, %key%y
        IniRead, %key%color, %iniFilePath%, wpcolor, %key%color
    }
    getwp1:=GetPixelColor(wp1x,wp1y)
    getwp2:=GetPixelColor(wp2x,wp2y)
    getwp3:=GetPixelColor(wp3x,wp3y)
    getwp4:=GetPixelColor(wp4x,wp4y)
    getwp5:=GetPixelColor(wp5x,wp5y)
    msgbox "手枪/手枪检测"`n"武器2颜色" %getwp2% "武器2本地颜色" %wp2color%`n"武器3颜色" %getwp3% "武器3本地颜色" %wp3color%`n"武器4颜色" %getwp4% "武器4本地颜色" %wp4color%`n"武器5颜色" %getwp5% "武器5本地颜色" %wp5color%`n
    saveType := "twpcolor"
    twp := ["2", "3", "4", "5"]
    Loop, % wp.MaxIndex()
    {
        skill := twp[A_Index]
        Loop
        {
            tooltip "请移动到手枪/火炬技能" %skill% "，11点方向按下"%savecolorkey%
            if GetKeyState(savecolorkey, "P")
            {
                MouseGetPos, xpos, ypos
                mousemove, xpos, ypos - 200
                sleep %sltime%
                PixelGetColor, color, %xpos%, %ypos%, RGB
                IniWrite, %xpos%, %iniFilePath%, %saveType%, twp%skill%x
                IniWrite, %ypos%, %iniFilePath%, %saveType%, twp%skill%y
                IniWrite, %color%, %iniFilePath%, %saveType%, twp%skill%color
                mousemove, xpos, ypos
                tooltip "手枪/火炬技能" %skill% "获取完毕"
                sleep jumptime
                tooltip
                break
            }
            if GetKeyState("ESC", "P")
            {
                tooltip "跳过"
                sleep jumptime
                tooltip
                break
            }
        }
    }
    keys := ["twp1","twp2","twp3","twp4","twp5"]
    for index, key in keys {
        IniRead, %key%x, %iniFilePath%, twpcolor, %key%x
        IniRead, %key%y, %iniFilePath%, twpcolor, %key%y
        IniRead, %key%color, %iniFilePath%, twpcolor, %key%color
    }
    gettwp1:=GetPixelColor(twp1x,twp1y)
    gettwp2:=GetPixelColor(twp2x,twp2y)
    gettwp3:=GetPixelColor(twp3x,twp3y)
    gettwp4:=GetPixelColor(twp4x,twp4y)
    gettwp5:=GetPixelColor(twp5x,twp5y)
    msgbox "手枪/火炬检测"`n"武器1颜色" %gettwp1% "武器1本地颜色" %twp1color%`n"武器2颜色" %gettwp2% "武器2本地颜色" %twp2color%`n"武器3颜色" %gettwp3% "武器3本地颜色" %twp3color%`n"武器4颜色" %gettwp4% "武器4本地颜色" %twp4color%`n"武器5颜色" %gettwp5% "武器5本地颜色" %twp5color%`n
    saveType := "tycolor"
    ty:= ["1","2", "3", "4", "5"]
    Loop, % ty.MaxIndex()
    {
        skill := ty[A_Index]
        Loop
        {
            if(skill==1)
            {
                tooltip "移动到通用1（慰籍咒语）11点处按下F9"
            }
            if(skill==2)
            {
                tooltip "移动到通用2（潜能咒语）11点处按下F9"
            }
            if(skill==3)
            {
                tooltip "移动到通用3（烈焰咒语）11点处按下F9"
            }
            if(skill==4)
            {
                tooltip "移动到通用4（净化火焰）11点处按下F9"
            }
            if(skill==5)
            {
                tooltip "移动到通用5（怒气冲天）11点处按下F9"
            }
            if GetKeyState(savecolorkey, "P")
            {
                MouseGetPos, xpos, ypos
                mousemove,xpos,ypos-200
                sleep %sltime%
                PixelGetColor, color, %xpos%, %ypos%, RGB
                IniWrite, %xpos%, %iniFilePath%, %saveType%, ty%skill%x
                IniWrite, %ypos%, %iniFilePath%, %saveType%, ty%skill%y
                IniWrite, %color%, %iniFilePath%, %saveType%, ty%skill%color
                mousemove, xpos, ypos
                tooltip "通用技能" %skill% "获取完毕"
                sleep jumptime
                tooltip
                break
            }
            if GetKeyState("ESC", "P")
            {
                tooltip "跳过"
                sleep jumptime
                tooltip
                break
            }
        }
    }
    keys := ["ty1", "ty2", "ty3", "ty4", "ty5"]
    for index, key in keys {
        IniRead, %key%x, %iniFilePath%, tycolor, %key%x
        IniRead, %key%y, %iniFilePath%, tycolor, %key%y
        IniRead, %key%color, %iniFilePath%, tycolor, %key%color
    }
    getty1:=GetPixelColor(ty1x,ty1y)
    getty2:=GetPixelColor(ty2x,ty2y)
    getty3:=GetPixelColor(ty3x,ty3y)
    getty4:=GetPixelColor(ty4x,ty4y)
    getty5:=GetPixelColor(ty5x,ty5y)
    msgbox "通用颜色检测"`n"通用1颜色" %getty1% "副武器1本地颜色" %ty1color%`n"通用2颜色" %getty2% "通用2本地颜色" %ty2color%`n"通用3颜色" %getty3% "通用3本地颜色" %ty3color%`n"通用4颜色" %getty4% "通用4本地颜色" %ty4color%`n"通用5颜色" %getty5% "通用5本地颜色" %ty5color%`n
    saveType := "fcolor"
    f:= ["1","2","3"]
    Loop, % f.MaxIndex()
    {
        skill := f[A_Index]
        Loop
        {
            tooltip "请移动到F1-F3技能" F%skill% "，11点方向按下"%savecolorkey%
            if GetKeyState(savecolorkey, "P")
            {
                MouseGetPos, xpos, ypos
                mousemove,xpos,ypos-200
                sleep %sltime%
                PixelGetColor, color, %xpos%, %ypos%, RGB
                IniWrite, %xpos%, %iniFilePath%, %saveType%, f%skill%x
                IniWrite, %ypos%, %iniFilePath%, %saveType%, f%skill%y
                IniWrite, %color%, %iniFilePath%, %saveType%, f%skill%color
                mousemove, xpos, ypos
                tooltip "F1-F3技能" F%skill% "获取完毕"
                sleep jumptime
                tooltip
                break
            }
            if GetKeyState("ESC", "P")
            {
                tooltip "跳过"
                sleep jumptime
                tooltip
                break
            }
        }
    }
    loop
    {
        tooltip "请在F1打开状态下，移动到F1技能11点处按下F9"
        if GetKeyState(savecolorkey, "P")
        {
            saveType := "fcolor"
            MouseGetPos, xpos, ypos
            mousemove,xpos,ypos-200
            sleep %sltime%
            PixelGetColor, color, %xpos%, %ypos%, RGB
            IniWrite, %xpos%, %iniFilePath%, %saveType%, point0x
            IniWrite, %ypos%, %iniFilePath%, %saveType%, point0y
            IniWrite, %color%, %iniFilePath%, %saveType%, point0color
            mousemove, xpos, ypos
            tooltip "豆子取色完毕"
            sleep jumptime
            tooltip
            break
        }
        if GetKeyState("ESC", "P")
        {
            tooltip "跳过"
            sleep jumptime
            tooltip
            break
        }
    }
    loop
    {
        tooltip "请在F1打开状态下，移动到武器技能二11点处按下F9"
        if GetKeyState(savecolorkey, "P")
        {
            saveType := "fcolor"
            MouseGetPos, xpos, ypos
            mousemove,xpos,ypos-200
            sleep %sltime%
            PixelGetColor, color, %xpos%, %ypos%, RGB
            IniWrite, %xpos%, %iniFilePath%, %saveType%, pointx
            IniWrite, %ypos%, %iniFilePath%, %saveType%, pointy
            IniWrite, %color%, %iniFilePath%, %saveType%, pointcolor
            mousemove, xpos, ypos
            tooltip "豆子取色完毕"
            sleep jumptime
            tooltip
            break
        }
        if GetKeyState("ESC", "P")
        {
            tooltip "跳过"
            sleep jumptime
            tooltip
            break
        }
    }
    loop
    {
        tooltip "请在F1打开状态下，移动到武器技能四使用后12点往左一点黑色部分处按下F9"
        if GetKeyState(savecolorkey, "P")
        {
            saveType := "fcolor"
            MouseGetPos, xpos, ypos
            mousemove,xpos,ypos-200
            sleep %sltime%
            PixelGetColor, color, %xpos%, %ypos%, RGB
            IniWrite, %xpos%, %iniFilePath%, %saveType%, point1x
            IniWrite, %ypos%, %iniFilePath%, %saveType%, point1y
            IniWrite, %color%, %iniFilePath%, %saveType%, point1color
            mousemove, xpos, ypos
            tooltip "幻象2位置"
            sleep jumptime
            tooltip
            break
        }
        if GetKeyState("ESC", "P")
        {
            tooltip "跳过"
            sleep jumptime
            tooltip
            break
        }
    }
    loop
    {
        tooltip "请在F1打开状态下，移动到武器技能五使用后12点往左一点黑色部分处按下F9"
        if GetKeyState(savecolorkey, "P")
        {
            saveType := "fcolor"
            MouseGetPos, xpos, ypos
            mousemove,xpos,ypos-200
            sleep %sltime%
            PixelGetColor, color, %xpos%, %ypos%, RGB
            IniWrite, %xpos%, %iniFilePath%, %saveType%, point2x
            IniWrite, %ypos%, %iniFilePath%, %saveType%, point2y
            IniWrite, %color%, %iniFilePath%, %saveType%, point2color
            mousemove, xpos, ypos
            tooltip "幻象2位置"
            sleep jumptime
            tooltip
            break
        }
        if GetKeyState("ESC", "P")
        {
            tooltip "跳过"
            sleep jumptime
            tooltip
            break
        }
    }
    loop
    {
        tooltip "请在慰籍咒语数字3处取色数字白色部分（建议用截屏模式取色）处按下F9"
        if GetKeyState(savecolorkey, "P")
        {
            saveType := "fcolor"
            MouseGetPos, xpos, ypos
            mousemove,xpos,ypos-200
            sleep %sltime%
            PixelGetColor, color, %xpos%, %ypos%, RGB
            IniWrite, %xpos%, %iniFilePath%, %saveType%, point3x
            IniWrite, %ypos%, %iniFilePath%, %saveType%, point3y
            IniWrite, %color%, %iniFilePath%, %saveType%, point3color
            mousemove, xpos, ypos
            tooltip "幻象2位置"
            sleep jumptime
            tooltip
            break
        }
        if GetKeyState("ESC", "P")
        {
            tooltip "跳过"
            sleep jumptime
            tooltip
            break
        }
    }
    loop
    {
        tooltip "请在慰籍咒语数字2处取色数字白色部分（建议用截屏模式取色）处按下F9"
        if GetKeyState(savecolorkey, "P")
        {
            saveType := "fcolor"
            MouseGetPos, xpos, ypos
            mousemove,xpos,ypos-200
            sleep %sltime%
            PixelGetColor, color, %xpos%, %ypos%, RGB
            IniWrite, %xpos%, %iniFilePath%, %saveType%, point4x
            IniWrite, %ypos%, %iniFilePath%, %saveType%, point4y
            IniWrite, %color%, %iniFilePath%, %saveType%, point4color
            mousemove, xpos, ypos
            tooltip "幻象2位置"
            sleep jumptime
            tooltip
            break
        }
        if GetKeyState("ESC", "P")
        {
            tooltip "跳过"
            sleep jumptime
            tooltip
            break
        }
    }
    loop
    {
        tooltip "请在火炬4第二段11点处按下F9"
        if GetKeyState(savecolorkey, "P")
        {
            saveType := "fcolor"
            MouseGetPos, xpos, ypos
            mousemove,xpos,ypos-200
            sleep %sltime%
            PixelGetColor, color, %xpos%, %ypos%, RGB
            IniWrite, %xpos%, %iniFilePath%, %saveType%, point5x
            IniWrite, %ypos%, %iniFilePath%, %saveType%, point5y
            IniWrite, %color%, %iniFilePath%, %saveType%, point5color
            mousemove, xpos, ypos
            tooltip "幻象2位置"
            sleep jumptime
            tooltip
            break
        }
        if GetKeyState("ESC", "P")
        {
            tooltip "跳过"
            sleep jumptime
            tooltip
            break
        }
    }
    loop
    {
        tooltip "请移动到切武器图标箭头处按下"%savecolorkey%
        if GetKeyState(savecolorkey, "P")
        {
            saveType := "qwq"
            MouseGetPos, xpos, ypos
            mousemove,xpos,ypos-200
            sleep %sltime%
            PixelGetColor, color, %xpos%, %ypos%, RGB
            IniWrite, %xpos%, %iniFilePath%, %saveType%, qwqx
            IniWrite, %ypos%, %iniFilePath%, %saveType%, qwqy
            IniWrite, %color%, %iniFilePath%, %saveType%, qwqcolor
            mousemove, xpos, ypos
            msgbox "切武器获取完毕"
            sleep jumptime
            tooltip
            break
        }
        if GetKeyState("ESC", "P")
        {
            tooltip "跳过"
            sleep jumptime
            tooltip
            break
        }
    }
    loop
    {
        tooltip "请移动到蔑视条处按下"%savecolorkey%
        if GetKeyState(savecolorkey, "P")
        {
            saveType := "mieshi"
            MouseGetPos, xpos, ypos
            mousemove,xpos,ypos-200
            sleep %sltime%
            PixelGetColor, color, %xpos%, %ypos%, RGB
            IniWrite, %xpos%, %iniFilePath%, %saveType%, mieshix
            IniWrite, %ypos%, %iniFilePath%, %saveType%, mieshiy
            IniWrite, %color%, %iniFilePath%, %saveType%, mieshicolor
            mousemove, xpos, ypos
            msgbox "蔑视条获取完毕,可开启热键循环"
            sleep jumptime
            tooltip
            break
        }
        if GetKeyState("ESC", "P")
        {
            tooltip "跳过"
            sleep jumptime
            tooltip
            break
        }
    }
return
savekey:
    IfWinExist, MyGui
    {
        WinActivate, MyGui
    }
    {
        Gui, MyGui: New , 0 , 热键
        Gui Add, Text, x10 y10 w50 h20, 武器
        Gui Add, Hotkey, x10 y30 w50 vwp1key Choose, %wp1key%
        Gui Add, Hotkey, x10 y60 w50 vwp2key Choose, %wp2key%
        Gui Add, Hotkey, x10 y90 w50 vwp3key Choose, %wp3key%
        Gui Add, Hotkey, x10 y120 w50 vwp4key Choose, %wp4key%
        Gui Add, Hotkey, x10 y150 w50 vwp5key Choose, %wp5key%
        Gui Add, Text, x80 y10 w50 h20, 通用
        Gui Add, Hotkey, x70 y30 w70 vty1key Choose, %ty1key%
        Gui Add, Hotkey, x70 y60 w70 vty2key Choose, %ty2key%
        Gui Add, Hotkey, x70 y90 w70 vty3key Choose, %ty3key%
        Gui Add, Hotkey, x70 y120 w70 vty4key Choose, %ty4key%
        Gui Add, Hotkey, x70 y150 w70 vty5key Choose, %ty5key%
        Gui Add, Text, x140 y10 w50 h20, F1-F5
        Gui Add, Hotkey, x150 y30 w70 vf1key Choose, %f1key%
        Gui Add, Hotkey, x150 y60 w70 vf2key Choose, %f2key%
        Gui Add, Hotkey, x150 y90 w70 vf3key Choose, %f3key%
        Gui Add, Hotkey, x150 y120 w70 vf4key Choose, %f4key%
        Gui Add, Hotkey, x150 y150 w70 vf5key Choose, %f5key%
        Gui Add, Text, x10 y185 w50 h20, 切
        Gui Add, edit, x30 y180 w70 vqwqkey Choose, %qwqkey%
        Gui Add, Text, x110 y185 w50 h20, 启
        Gui Add, edit, x130 y180 w70 vstartkey Choose, %startkey%
        Gui Add, Text, x10 y210 w50 h20, 取
        Gui Add, Hotkey, x30 y210 w70 vsavecolorkey Choose, %savecolorkey%
        Gui Add, Text, x110 y210 w50 h20, 存
        Gui Add, Hotkey, x130 y210 w70 vsavekey Choose, %savekey%
        Gui Add, Text, x10 y240 w50 h20, 开
        Gui, Add, Edit,x30 y240 w70 vstartfont ,%startfont%
        Gui Add, Text, x110 y240 w50 h20, 全局延迟
        Gui Add, edit, x165 y240 w30 valltime , %alltime%
        Gui Add, Button, x90 y270 w50 h30 gSaveButton default, 保存
        Gui Show
    }
return
SaveButton:
    gui Submit
    saveType := "Hotkeys"
    IniWrite, %wp1key%, %iniFilePath%, %saveType%, wp1key
    IniWrite, %wp2key%, %iniFilePath%, %saveType%, wp2key
    IniWrite, %wp3key%, %iniFilePath%, %saveType%, wp3key
    IniWrite, %wp4key%, %iniFilePath%, %saveType%, wp4key
    IniWrite, %wp5key%, %iniFilePath%, %saveType%, wp5key
    IniWrite, %ty1key%, %iniFilePath%, %saveType%, ty1key
    IniWrite, %ty2key%, %iniFilePath%, %saveType%, ty2key
    IniWrite, %ty3key%, %iniFilePath%, %saveType%, ty3key
    IniWrite, %ty4key%, %iniFilePath%, %saveType%, ty4key
    IniWrite, %ty5key%, %iniFilePath%, %saveType%, ty5key
    IniWrite, %f1key%, %iniFilePath%, %saveType%, f1key
    IniWrite, %f2key%, %iniFilePath%, %saveType%, f2key
    IniWrite, %f3key%, %iniFilePath%, %saveType%, f3key
    IniWrite, %f4key%, %iniFilePath%, %saveType%, f4key
    IniWrite, %f5key%, %iniFilePath%, %saveType%, f5key
    IniWrite, %qwqkey%, %iniFilePath%, %saveType%, qwqkey
    IniWrite, %startkey%, %iniFilePath%, %saveType%, startkey
    IniWrite, %savecolorkey%, %iniFilePath%, %saveType%, savecolorkey
    IniWrite, %savekey%, %iniFilePath%, %saveType%, savekey
    IniWrite, %kai%, %iniFilePath%, %saveType%, startfont
    IniWrite, %alltime%, %iniFilePath%,sleep, alltime
    MsgBox, 保存成功！
return
GetPixelColor(x,y)
{
    PixelGetColor, color, x, y, RGB
return color
}
SendLoop(key, loopCount) {
    global alltime

    SendInput, {%key%}
    sleep, (loopCount-alltime)
}